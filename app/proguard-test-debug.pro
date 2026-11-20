# Rules for the debug instrumentation test APK only.
#
# androidx.test references annotations that are compile-time only and are not
# part of Android: Error Prone's annotations and the JDK annotation-processing
# API they point at. They are never loaded at runtime, so R8 only needs to stop
# treating them as missing classes. Release APKs never include these rules.
-dontwarn com.google.errorprone.annotations.**
-dontwarn javax.lang.model.**
