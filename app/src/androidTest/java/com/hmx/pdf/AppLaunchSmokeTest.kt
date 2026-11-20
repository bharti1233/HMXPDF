package com.hmx.pdf

import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Minimal lifecycle smoke test for cloud device runs.
 *
 * It launches the real launcher activity on a freshly installed debug build,
 * checks that the window is attached, backgrounds and resumes the activity,
 * and recreates it. It never opens a user file or requests a permission.
 */
@RunWith(AndroidJUnit4::class)
class AppLaunchSmokeTest {

    @Test
    fun launcherActivityResumes() {
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            scenario.onActivity { activity ->
                assertTrue(
                    "The activity window must be attached to the device window manager",
                    activity.window.decorView.isAttachedToWindow
                )
                assertTrue(
                    "The launcher activity must reach RESUMED",
                    activity.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
                )
            }
        } finally {
            scenario.close()
        }
    }

    @Test
    fun survivesBackgroundResumeAndRecreation() {
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            scenario.moveToState(Lifecycle.State.CREATED)
            scenario.moveToState(Lifecycle.State.RESUMED)
            scenario.recreate()
            scenario.onActivity { activity ->
                assertTrue(
                    "The activity must still be usable after recreation",
                    activity.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
                )
            }
        } finally {
            scenario.close()
        }
    }
}
