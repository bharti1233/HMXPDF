package com.hmx.pdf.backend

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RetryPolicyTest {
    @Test
    fun retriesOnlyTransientFailures() {
        assertTrue(RetryPolicy.shouldRetry(1, null))
        assertTrue(RetryPolicy.shouldRetry(1, 429))
        assertTrue(RetryPolicy.shouldRetry(1, 500))
        assertTrue(RetryPolicy.shouldRetry(1, 503))
        assertFalse(RetryPolicy.shouldRetry(1, 400))
        assertFalse(RetryPolicy.shouldRetry(1, 401))
        assertFalse(RetryPolicy.shouldRetry(1, 403))
        assertFalse(RetryPolicy.shouldRetry(1, 404))
    }

    @Test
    fun retryCountIsBounded() {
        assertTrue(RetryPolicy.shouldRetry(2, 500))
        assertFalse(RetryPolicy.shouldRetry(3, 500))
        assertFalse(RetryPolicy.shouldRetry(4, null))
    }

    @Test
    fun backoffGrowsButStaysSmall() {
        assertTrue(RetryPolicy.backoffMillis(2) > RetryPolicy.backoffMillis(1))
        assertTrue(RetryPolicy.backoffMillis(3) <= 2_000L)
    }
}
