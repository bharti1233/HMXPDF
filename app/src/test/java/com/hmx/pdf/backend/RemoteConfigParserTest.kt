package com.hmx.pdf.backend

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RemoteConfigParserTest {
    private val valid = """
        {"data":{"version":8,"config":{"schema_version":1,"min_supported_app_version_code":6,
        "features":{"url_to_pdf":true,"ocr":false},"announcement":{"enabled":true,"message":"hello","url":""},
        "limits":{"max_document_mb":200,"max_pages":300}},"published_at":"2026-11-21T00:00:00Z"}}
    """.trimIndent()

    @Test
    fun parsesPublishedConfiguration() {
        val snapshot = RemoteConfigParser.parse(valid)
        assertNotNull(snapshot)
        assertEquals(8L, snapshot!!.version)
        assertTrue(FeatureFlags.isEnabled(snapshot, FeatureFlags.URL_TO_PDF))
        assertFalse(FeatureFlags.isEnabled(snapshot, FeatureFlags.OCR))
        assertEquals("hello", snapshot.config.announcement.message)
        assertEquals(300, snapshot.config.limits.maxPages)
    }

    @Test
    fun rejectsMalformedOrUnknownDocuments() {
        assertNull(RemoteConfigParser.parse("not json"))
        assertNull(RemoteConfigParser.parse("""{"data":{"version":1,"config":{"schema_version":2}}}"""))
        assertNull(
            RemoteConfigParser.parse(
                """{"data":{"version":1,"config":{"schema_version":1,"features":{"tracking":true}}}}""",
            ),
        )
    }

    @Test
    fun defaultsAreSafeWhenNoConfigExists() {
        assertFalse(FeatureFlags.isEnabled(null, FeatureFlags.IMAGE_EDITOR))
        assertTrue(FeatureFlags.isEnabled(null, FeatureFlags.OCR, default = true))
    }

    @Test
    fun encodeRoundTripPreservesSnapshot() {
        val snapshot = RemoteConfigParser.parse(valid)!!
        val restored = RemoteConfigParser.parse(RemoteConfigParser.encode(snapshot))
        assertNotNull(restored)
        assertEquals(snapshot.version, restored!!.version)
        assertEquals(snapshot.config.announcement.message, restored.config.announcement.message)
    }
}
