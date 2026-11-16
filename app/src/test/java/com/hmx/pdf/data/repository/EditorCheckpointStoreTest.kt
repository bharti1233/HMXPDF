package com.hmx.pdf.data.repository

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/**
 * The editor checkpoint store (Phase 4.1): commit/find/clear on the File-rooted core — identity
 * by URI (never display name), validate-before-commit with an atomic rename (the prior good
 * checkpoint survives every failure, disk-full included), generation increments, and refusal of
 * checkpoints that no longer match their recorded bytes.
 */
class EditorCheckpointStoreTest {

    private val CT_MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"

    /** A minimal valid DOCX package (what validateOfficePackage requires). */
    private fun docx(text: String): ByteArray {
        val bos = java.io.ByteArrayOutputStream()
        ZipOutputStream(bos).use { z ->
            z.putNextEntry(ZipEntry("[Content_Types].xml"))
            z.write((("<?xml version=\"1.0\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
                + "<Override PartName=\"/word/document.xml\" ContentType=\"$CT_MAIN\"/></Types>")).toByteArray())
            z.closeEntry()
            z.putNextEntry(ZipEntry("word/document.xml"))
            z.write((("<?xml version=\"1.0\"?><w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
                + "<w:body><w:p><w:r><w:t>$text</w:t></w:r></w:p></w:body></w:document>")).toByteArray())
            z.closeEntry()
        }
        return bos.toByteArray()
    }

    private fun root(): File =
        java.nio.file.Files.createTempDirectory("checkpoint-root").toFile().apply { deleteOnExit() }

    private fun complete(text: String): File =
        File.createTempFile("complete", ".docx").apply { writeBytes(docx(text)); deleteOnExit() }

    // ── commit / find round trip ───────────────────────────────────────────────

    @Test
    fun commitIsDiscoverableWithFullMetadata() {
        val r = root()
        val ck = EditorCheckpointStore.commit(r, "content://doc/1", "report.docx", "docx", complete("v1"), "hash-0")!!
        assertEquals("report.docx", ck.displayName)
        assertEquals("docx", ck.kind)
        assertEquals("content://doc/1", ck.originalUri)
        assertEquals("hash-0", ck.originalHash)
        assertEquals(1, ck.generation)
        assertEquals(ck.checkpointHash, EditorCheckpointStore.sha256(ck.file))
        assertTrue(ck.createdAt > 0)
        assertTrue(ck.sessionId.isNotBlank())
        // find() by identity returns the same checkpoint.
        assertEquals(ck.checkpointHash, EditorCheckpointStore.find(r, "content://doc/1")!!.checkpointHash)
    }

    @Test
    fun displayNamesDoNotIdentifyDocuments() {
        val r = root()
        EditorCheckpointStore.commit(r, "content://doc/1", "same name.docx", "docx", complete("a"), null)
        EditorCheckpointStore.commit(r, "content://doc/2", "same name.docx", "docx", complete("b"), null)
        assertNotEquals(
            EditorCheckpointStore.find(r, "content://doc/1")!!.checkpointHash,
            EditorCheckpointStore.find(r, "content://doc/2")!!.checkpointHash
        )
    }

    @Test
    fun aNewerCommitSupersedesAndIncrementsTheGeneration() {
        val r = root()
        EditorCheckpointStore.commit(r, "content://doc/1", "d.docx", "docx", complete("v1"), "hash-0")
        val second = EditorCheckpointStore.commit(r, "content://doc/1", "d.docx", "docx", complete("v2"), "hash-0")!!
        assertEquals(2, second.generation)
        assertEquals("hash-0", second.originalHash) // sticky: describes the opened destination
        assertEquals(second.checkpointHash, EditorCheckpointStore.find(r, "content://doc/1")!!.checkpointHash)
    }

    // ── failure leaves the last known good checkpoint intact ──────────────────

    @Test
    fun aFailedCommitKeepsThePriorCheckpoint() {
        val r = root()
        val first = EditorCheckpointStore.commit(r, "content://doc/1", "d.docx", "docx", complete("v1"), "hash-0")!!
        // An invalid "package" cannot commit: the previous checkpoint stays discoverable, with
        // its own generation and hash (the write-interruption boundary the roadmap asks for).
        val bad = File.createTempFile("bad", ".docx").apply { writeBytes("not a zip".toByteArray()); deleteOnExit() }
        assertNull(EditorCheckpointStore.commit(r, "content://doc/1", "d.docx", "docx", bad, "hash-0"))
        val found = EditorCheckpointStore.find(r, "content://doc/1")!!
        assertEquals(first.checkpointHash, found.checkpointHash)
        assertEquals(1, found.generation)
    }

    @Test
    fun aCorruptedCheckpointIsRefusedAndCleaned() {
        val r = root()
        val ck = EditorCheckpointStore.commit(r, "content://doc/1", "d.docx", "docx", complete("v1"), null)!!
        ck.file.writeBytes(ck.file.readBytes().copyOfRange(0, 10)) // truncate: hash no longer matches
        assertNull(EditorCheckpointStore.find(r, "content://doc/1"))
        assertFalse(ck.directory.exists()) // unusable leftovers removed entirely
    }

    @Test
    fun clearRemovesEverythingForTheIdentity() {
        val r = root()
        val ck = EditorCheckpointStore.commit(r, "content://doc/1", "d.docx", "docx", complete("v1"), null)!!
        EditorCheckpointStore.clear(r, "content://doc/1")
        assertNull(EditorCheckpointStore.find(r, "content://doc/1"))
        assertFalse(ck.directory.exists())
    }

    @Test
    fun unknownIdentityHasNoCheckpoint() {
        val r = root()
        assertNull(EditorCheckpointStore.find(r, "content://never-opened"))
    }

    // ── context overloads resolve to the no-backup root ────────────────────────

    @Test
    fun contextOverloadsKeyTheSameIdentityTheSameWay() {
        // The Context half must key the same identity the same way (find and clear coordinate
        // through it); keys are sha-256 hex, so equal identities collide and others do not.
        val key = EditorCheckpointStore.keyFor("content://doc/1")
        assertEquals(key, EditorCheckpointStore.keyFor("content://doc/1"))
        assertNotEquals(key, EditorCheckpointStore.keyFor("content://doc/2"))
        assertEquals(64, key.length)
    }
}
