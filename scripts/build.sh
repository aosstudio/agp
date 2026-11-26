#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
python=${PYTHON:-python3}
"$python" scripts/inputs.py
version=$("$python" scripts/inputs.py version)
archived="aosstudio-agp-$version-maven"
inputs="$root/out/inputs"
work=$(mktemp -d "$root/out/build.XXXXXXXX")
trap 'rm -rf -- "$work"' EXIT
export LC_ALL=C TZ=UTC TMPDIR="$work/tmp"
unset JDK_JAVA_OPTIONS JAVA_TOOL_OPTIONS _JAVA_OPTIONS CLASSPATH
package="$work/$archived"
mkdir -p "$work/jdk" "$TMPDIR" "$package/maven" out/dist
tar -xzf "$inputs/tools/aosstudio-jdk-21.0.13.1-2-linux-x86_64.tar.gz" -C "$work/jdk"
unzip -q "$inputs/tools/gradle-9.6.0-bin.zip" -d "$work"
gradle="$work/gradle-9.6.0"
jdk="$work/jdk"
"$jdk/bin/java" -version

library_paths=$("$python" scripts/inputs.py classpath)
libraries=("$gradle"/lib/*.jar "$gradle"/lib/plugins/*.jar)
library_paths="${library_paths//$'\n'/:}:$(IFS=:; printf '%s' "${libraries[*]}")"
r8="$inputs/tools/aosstudio-r8-9.5.29-agp.jar"
builder="$package/maven/com/android/tools/build/builder/$version/builder-$version.jar"

for module in builder gradle; do
  mkdir -p "$work/$module"
  cd "$work/$module"
  "$python" "$root/scripts/package_agp.py" sources src --module "$module"
  mkdir classes
  find src -type f -name '*.kt' | sort > kotlin-sources.txt
  find src -type f -name '*.java' | sort > java-sources.txt
  wc -l kotlin-sources.txt java-sources.txt
  if [[ "$module" == builder ]]; then
    classpath="$r8:$library_paths"
    module_name=builder
  else
    classpath="$builder:$library_paths"
    module_name="gradle-core"
  fi

  "$jdk/bin/java" -Xmx10g "-Djava.io.tmpdir=$TMPDIR" -cp "$gradle/lib/*" \
    org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib -no-reflect -jvm-target 17 \
    -language-version 2.2 -Xjspecify-annotations=warn -Xjsr305=warn -module-name "$module_name" \
    -classpath "$classpath" "-Xjava-source-roots=$PWD/src" -d classes @kotlin-sources.txt
  "$jdk/bin/javac" -J-Xmx5g "-J-Djava.io.tmpdir=$TMPDIR" --release 17 -proc:none -encoding UTF-8 \
    -classpath "classes:$classpath" -d classes @java-sources.txt
  "$python" "$root/scripts/package_agp.py" package "$package/maven" --module "$module" --classes classes
done

"$python" "$root/scripts/package_agp.py" markers "$package/maven"
install -m 0644 "$root/LICENSE" "$package/LICENSE"
install -m 0644 "$root/locks/inputs.json" "$package/inputs.json"
tar --sort=name --owner=0 --group=0 --numeric-owner --mtime=@1794787200 \
  -czf "$work/$archived.tar.gz" -C "$work" "$archived"
mv -- "$work/$archived.tar.gz" "$root/out/dist/"
