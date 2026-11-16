package com.hmx.pdf.data.repository

import android.content.Context
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.Properties
import java.util.UUID

/**
 * Durable editor checkpoints for unsaved edits (Phase 4.1): one complete, validated package per
 * document identity under [Context.getNoBackupFilesDir], so a process death between saves still
 * recovers the last committed checkpoint.
 *
 * Identity is the sha-256 of the source URI string — never the display name (two documents may
 * share a name; a URI does not change because the user renamed it). One checkpoint is kept per
 * document: a commit writes a temp copy, validates it, and atomically renames it over the
 * previous checkpoint, so the last known-good checkpoint survives every interruption — including
 * disk-full (the failed temp is deleted and the prior files are untouched) and death before the
 * metadata rename (the previous metadata still names the previous checkpoint).
 *
 * [originalHash] is the hash of the destination as it was when the document was opened; recovery
 * compares it against the current original to label conflicts ("the file changed since this
 * checkpoint"). The journal at [SaveRecovery] remains the owner of manual-save crash safety;
 * this store only covers edits that were never saved. The [Context]-bound halves delegate to the
 * File-rooted core, which JVM tests exercise directly.
 */
internal object EditorCheckpointStore {

    /** Bump when the metadata layout changes; readers refuse unknown versions. */
    const val VERSION = 1
    private const val ROOT = "editor-checkpoints"
    private const val META = "meta.properties"

    /** One recoverable checkpoint: the committed package plus its identity metadata. */
    data class Checkpoint(
        val docKey: String,
        val directory: File,
        val file: File,
        val kind: String,
        val displayName: String,
        val originalUri: String,
        val originalHash: String,
        val checkpointHash: String,
        val generation: Long,
        val createdAt: Long,
        val sessionId: String
    )

    /** Stable per-document key: sha-256 of the identity string, hex-encoded. */
    fun keyFor(identity: String): String =
        MessageDigest.getInstance("SHA-256").digest(identity.toByteArray())
            .joinToString("") { "%02x".format(it) }

    // ── Context API ────────────────────────────────────────────────────────────

    /** Commits [complete] as the newest checkpoint of [sourceUri]; null when the commit failed. */
    fun commit(
        context: Context,
        sourceUri: String?,
        displayName: String,
        kind: String,
        complete: File,
        originalHash: String?
    ): Checkpoint? = sourceUri?.takeIf { it.isNotBlank() }?.let {
        commit(File(context.noBackupFilesDir, ROOT), it, displayName, kind, complete, originalHash)
    }

    /** The committed checkpoint of [sourceUri], when one exists and still validates. */
    fun find(context: Context, sourceUri: String): Checkpoint? =
        find(File(context.noBackupFilesDir, ROOT), sourceUri)

    fun clear(context: Context, sourceUri: String) =
        clear(File(context.noBackupFilesDir, ROOT), sourceUri)

    // ── File-rooted core (JVM-testable) ───────────────────────────────────────

    internal fun commit(
        root: File,
        identity: String,
        displayName: String,
        kind: String,
        complete: File,
        originalHash: String? = null
    ): Checkpoint? {
        require(kind == "docx" || kind == "xlsx") { "Unsupported document kind" }
        if (!complete.isFile || complete.length() <= 0L) return null
        val dir = File(root, keyFor(identity))
        val tmp = File(dir, "checkpoint.tmp")
        val target = File(dir, "checkpoint.$kind")
        val metaTmp = File(dir, "$META.tmp")
        val meta = File(dir, META)
        try {
            if (!dir.isDirectory && !dir.mkdirs()) return null
            copyValidated(complete, tmp, kind) ?: return null
            val hash = sha256(tmp)
            // Commit point 1: the package. The rename is atomic on the same volume, so a reader
            // sees either the previous checkpoint or this one — never a partial file.
            if (!tmp.renameTo(target)) return null
            val previous = readCheckpoint(dir, kind)
            // Commit point 2: the metadata that makes it discoverable. Until this rename the
            // previous metadata (if any) still describes the previous checkpoint. The original
            // hash is sticky: it describes the opened destination, not the checkpoint.
            val properties = Properties().apply {
                setProperty("version", VERSION.toString())
                setProperty("identity", identity)
                setProperty("displayName", displayName)
                setProperty("kind", kind)
                setProperty("checkpointHash", hash)
                setProperty("generation", ((previous?.generation ?: 0L) + 1L).toString())
                setProperty("createdAt", System.currentTimeMillis().toString())
                setProperty("sessionId", UUID.randomUUID().toString())
                setProperty("originalHash", originalHash ?: previous?.originalHash ?: "")
            }
            FileOutputStream(metaTmp).use { out ->
                out.fd.sync()
                properties.store(out, "HMXPDF editor checkpoint")
            }
            if (!metaTmp.renameTo(meta)) return null
            return readCheckpoint(dir, kind)
        } catch (cancellation: java.util.concurrent.CancellationException) {
            tmp.delete(); metaTmp.delete()
            throw cancellation
        } catch (expected: Exception) {
            // Disk-full, interruption, anything: remove our partials, leave the prior checkpoint.
            tmp.delete(); metaTmp.delete()
            return null
        }
    }

    /**
     * Copies [from] to [to] and validates the copy as a [kind] package *before* it can become a
     * checkpoint; returns the copy, or null (with [to] removed) when the package is invalid.
     */
    private fun copyValidated(from: File, to: File, kind: String): File? {
        try {
            from.inputStream().use { input ->
                FileOutputStream(to).use { out ->
                    input.copyTo(out)
                    out.fd.sync()
                }
            }
            return if (SaveRecovery.validateOfficePackage(to, kind)) to else { to.delete(); null }
        } catch (cancellation: java.util.concurrent.CancellationException) {
            to.delete()
            throw cancellation
        } catch (expected: Exception) {
            to.delete()
            return null
        }
    }

    internal fun find(root: File, identity: String): Checkpoint? {
        val dir = File(root, keyFor(identity))
        if (!dir.isDirectory) return null
        val kind = listOf("docx", "xlsx").firstOrNull { File(dir, "checkpoint.$it").isFile } ?: return run {
            // Metadata without a package: unusable leftovers, clean them up.
            dir.deleteRecursively()
            null
        }
        return readCheckpoint(dir, kind)?.takeIf { checkpoint ->
            // A checkpoint that no longer matches its recorded bytes is not a recovery source.
            sha256(checkpoint.file) == checkpoint.checkpointHash
        } ?: run {
            // Unusable leftovers (corrupt/truncated): clean them so they never surface later.
            dir.deleteRecursively()
            null
        }
    }

    private fun readCheckpoint(dir: File, kind: String): Checkpoint? {
        val meta = File(dir, META)
        if (!meta.isFile) return null
        val properties = Properties()
        try {
            meta.inputStream().use { properties.load(it) }
        } catch (expected: Exception) {
            return null
        }
        if (properties.getProperty("version")?.toIntOrNull() != VERSION) return null
        val file = File(dir, "checkpoint.$kind")
        if (!file.isFile) return null
        val identity = properties.getProperty("identity") ?: return null
        return Checkpoint(
            docKey = keyFor(identity),
            directory = dir,
            file = file,
            kind = properties.getProperty("kind") ?: kind,
            displayName = properties.getProperty("displayName") ?: "Document",
            originalUri = identity,
            originalHash = properties.getProperty("originalHash") ?: "",
            checkpointHash = properties.getProperty("checkpointHash") ?: "",
            generation = properties.getProperty("generation")?.toLongOrNull() ?: 0L,
            createdAt = properties.getProperty("createdAt")?.toLongOrNull() ?: 0L,
            sessionId = properties.getProperty("sessionId") ?: ""
        )
    }

    internal fun clear(root: File, identity: String) {
        File(root, keyFor(identity)).deleteRecursively()
    }

    internal fun sha256(file: File): String =
        MessageDigest.getInstance("SHA-256").run {
            file.inputStream().use { input ->
                val buffer = ByteArray(64 * 1024)
                while (true) {
                    val read = input.read(buffer)
                    if (read < 0) break
                    update(buffer, 0, read)
                }
            }
            digest().joinToString("") { "%02x".format(it) }
        }
}
