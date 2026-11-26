# Build AGP

Build on Linux x86-64 with Python 3.12 or later, GNU Make, Bash, curl, tar, unzip and flock.

```sh
make build
make verify
```

`make fetch` prepares the locked inputs separately. The build uses published AOSStudio JDK and R8 assets and the Gradle 9.6.0 distribution. The current pins and upstream Maven URLs are in [the input lock](../locks/inputs.json). The JDK and R8 Nightly URLs are mutable. Review changed assets before updating their pinned digests.

The build compiles Java and Kotlin from the 9.5.2 Maven source archives, using the published generated Java files at their canonical paths. The published implementation archives supply the resource files. The builder incorporates the published AOSStudio R8 9.5.29 JAR entries. The build updates the Gradle Module Metadata digests to describe the rebuilt JARs and retains the upstream notices.

The output is `out/dist/aosstudio-agp-9.5.2-maven.tar.gz`. Its `maven/` directory contains the main and builder modules, POMs, module metadata and plugin marker POMs. Unpack it and configure Gradle's `pluginManagement.repositories` with that Maven directory for the rebuilt modules and their markers. Keep the usual approved upstream repositories for the other dependencies. Projects use the standard `com.android.application` and `com.android.library` plugin IDs with version `9.5.2`. The Maven archive contains JVM artifacts for use with a supported host JDK.

The default verification resolves the plugin through its marker in a clean Gradle environment, checks that Gradle loads the rebuilt modules and checks the embedded R8 classes and API database. To run the APK verification, provide an installed AOSStudio API 37.0 SDK with Build Tools 36.0.0.

```sh
make verify SDK_ROOT=/path/to/aosstudio-sdk
```

APK verification uses the SDK's AAPT2 and runs offline. It builds and verifies Java and Kotlin APKs, then runs AGP's minification task and checks that R8 removes an unused class. Use `make check` with ShellCheck and the Python lint dependencies in `ci/lint-requirements.txt` for static checks. The pinned lint wheels target CPython 3.14 on Linux x86-64.
