#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
python=${PYTHON:-python3}
version=$("$python" scripts/inputs.py version)
inputs="$root/out/inputs"
work=$(mktemp -d "$root/out/verify.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
export LC_ALL=C TZ=UTC TMPDIR="$work/tmp"
export JAVA_HOME="$work/jdk" GRADLE_USER_HOME="$work/gradle-user" ANDROID_USER_HOME="$work/android-user"
export PATH="$JAVA_HOME/bin:$PATH"
unset JDK_JAVA_OPTIONS JAVA_TOOL_OPTIONS _JAVA_OPTIONS CLASSPATH ANDROID_SDK_ROOT
mkdir -p "$JAVA_HOME" "$TMPDIR" "$GRADLE_USER_HOME" "$ANDROID_USER_HOME" "$work/empty-sdk"
tar -xzf "$inputs/tools/aosstudio-jdk-21.0.13.1-2-linux-x86_64.tar.gz" -C "$JAVA_HOME"
unzip -q "$inputs/tools/gradle-9.6.0-bin.zip" -d "$work"
archive="aosstudio-agp-$version-maven"
tar -xzf "out/dist/$archive.tar.gz" -C "$work"
export AOS_AGP_MAVEN="$work/$archive/maven" AOS_AGP_DEPENDENCIES="$inputs/dependencies"
"$python" scripts/package_agp.py verify "$AOS_AGP_MAVEN"
"$JAVA_HOME/bin/java" -cp "$AOS_AGP_MAVEN/com/android/tools/build/builder/$version/builder-$version.jar" \
  com.android.tools.r8.R8 --version | grep -F 'R8 9.5.29'

cp -a tests/project "$work/project"
gradle=("$work/gradle-9.6.0/bin/gradle" --offline --no-daemon --console=plain
  --project-dir "$work/project" -Dorg.gradle.vfs.watch=false "-Djava.io.tmpdir=$TMPDIR"
  -Pandroid.builder.sdkDownload=false)
export ANDROID_HOME="$work/empty-sdk"
"${gradle[@]}" :java-app:inspectAgp :kotlin-app:inspectAgp

if [[ -n "${SDK_ROOT:-}" ]]; then
  export ANDROID_HOME
  ANDROID_HOME=$(realpath -- "$SDK_ROOT")
  tools="$ANDROID_HOME/build-tools/36.0.0"
  test -f "$ANDROID_HOME/platforms/android-37.0/android.jar"
  test -x "$tools/aapt2"
  "${gradle[@]}" "-Pandroid.aapt2FromMavenOverride=$tools/aapt2" \
    :java-app:assembleDebug :kotlin-app:assembleDebug
  for app in java-app kotlin-app; do
    apk="$work/project/$app/build/outputs/apk/debug/$app-debug.apk"
    "$tools/zipalign" -c -P 16 4 "$apk"
    "$tools/apksigner" verify --min-sdk-version 24 --max-sdk-version 37 --verbose "$apk" |
      grep -F 'Verified using v2 scheme (APK Signature Scheme v2): true'
  done

  "${gradle[@]}" "-Pandroid.aapt2FromMavenOverride=$tools/aapt2" -PverifyMinify :java-app:assembleDebug
  grep -Fx 'sdk.probe.Unused' "$work/project/java-app/build/outputs/mapping/debug/usage.txt"
fi
printf 'AGP %s package verified\n' "$version"
