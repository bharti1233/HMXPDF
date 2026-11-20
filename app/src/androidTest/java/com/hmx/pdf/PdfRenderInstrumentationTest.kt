package com.hmx.pdf

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.pdmodel.PDPage
import com.tom_roush.pdfbox.pdmodel.PDPageContentStream
import com.tom_roush.pdfbox.pdmodel.common.PDRectangle
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * On-device PDF rendering check for cloud device runs.
 *
 * The fixture is generated inside the test from a blank PdfBox page with a solid
 * black square, so the test proves that the device can rasterize a real PDF
 * through the platform renderer on this ABI. No user file is read.
 */
@RunWith(AndroidJUnit4::class)
class PdfRenderInstrumentationTest {

    @Test
    fun rendersGeneratedPdfOnDevice() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val pdfFile = File(context.cacheDir, "hmxpdf-cloud-fixture.pdf")
        if (pdfFile.exists()) pdfFile.delete()

        PDDocument().use { document ->
            val page = PDPage(PDRectangle(200f, 200f))
            document.addPage(page)
            PDPageContentStream(document, page).use { content ->
                content.setNonStrokingColor(0f, 0f, 0f)
                content.addRect(20f, 20f, 120f, 120f)
                content.fill()
            }
            document.save(pdfFile)
        }

        assertTrue("Generated fixture is missing", pdfFile.length() > 0)

        ParcelFileDescriptor.open(pdfFile, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
            PdfRenderer(descriptor).use { renderer ->
                assertEquals("Generated PDF must contain exactly one page", 1, renderer.pageCount)
                renderer.openPage(0).use { page ->
                    val bitmap = Bitmap.createBitmap(page.width, page.height, Bitmap.Config.ARGB_8888)
                    bitmap.eraseColor(Color.WHITE)
                    page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)

                    assertTrue("Rendered page has no pixels", bitmap.width > 0 && bitmap.height > 0)
                    assertTrue(
                        "Rendered page does not contain the black square; rasterization produced a blank page",
                        hasDarkPixel(bitmap)
                    )
                    bitmap.recycle()
                }
            }
        }

        pdfFile.delete()
    }

    private fun hasDarkPixel(bitmap: Bitmap): Boolean {
        val stepX = (bitmap.width / 40).coerceAtLeast(1)
        val stepY = (bitmap.height / 40).coerceAtLeast(1)
        var y = 0
        while (y < bitmap.height) {
            var x = 0
            while (x < bitmap.width) {
                val pixel = bitmap.getPixel(x, y)
                if (Color.red(pixel) < 64 && Color.green(pixel) < 64 && Color.blue(pixel) < 64) {
                    return true
                }
                x += stepX
            }
            y += stepY
        }
        return false
    }
}
