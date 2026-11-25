plugins {
    java
    id("org.jetbrains.intellij.platform") version "2.20.0"
}
version = "0.2.0"
repositories {
    mavenCentral()
    intellijPlatform { defaultRepositories() }
}
dependencies {
    intellijPlatform { clion("2025.3") }
}
java { toolchain { languageVersion.set(JavaLanguageVersion.of(21)) } }
intellijPlatform {
    pluginConfiguration { ideaVersion { sinceBuild.set("253") } }
}
