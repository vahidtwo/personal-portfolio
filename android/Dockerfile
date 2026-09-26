# Build debug APK for sideload (my-inventory.apk).
# Override when Docker Hub is blocked: --build-arg BASE_IMAGE=hub.hamdocker.ir/eclipse-temurin:17-jdk-jammy
ARG BASE_IMAGE=eclipse-temurin:17-jdk-jammy
FROM ${BASE_IMAGE} AS builder

ENV ANDROID_HOME=/opt/android-sdk
ENV GRADLE_HOME=/opt/gradle
ENV PATH="${PATH}:${ANDROID_HOME}/platform-tools:${GRADLE_HOME}/bin"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fL -o /tmp/gradle.zip https://services.gradle.org/distributions/gradle-8.7-bin.zip \
    && unzip -q /tmp/gradle.zip -d /opt \
    && mv /opt/gradle-8.7 /opt/gradle \
    && rm /tmp/gradle.zip

RUN mkdir -p "${ANDROID_HOME}" \
    && curl -fL -o /tmp/platform-tools.zip \
      "https://redirector.gvt1.com/edgedl/android/repository/platform-tools_r35.0.2-linux.zip" \
    && unzip -q /tmp/platform-tools.zip -d "${ANDROID_HOME}" \
    && curl -fL -o /tmp/build-tools.zip \
      "https://redirector.gvt1.com/edgedl/android/repository/build-tools_r34-linux.zip" \
    && unzip -q /tmp/build-tools.zip -d "${ANDROID_HOME}" \
    && mkdir -p "${ANDROID_HOME}/build-tools/34.0.0" \
    && mv "${ANDROID_HOME}/android-14/"* "${ANDROID_HOME}/build-tools/34.0.0/" \
    && rmdir "${ANDROID_HOME}/android-14" \
    && curl -fL -o /tmp/platform.zip \
      "https://redirector.gvt1.com/edgedl/android/repository/platform-34-ext7_r03.zip" \
    && unzip -q /tmp/platform.zip -d "${ANDROID_HOME}" \
    && mkdir -p "${ANDROID_HOME}/platforms" \
    && mv "${ANDROID_HOME}/android-34" "${ANDROID_HOME}/platforms/android-34" \
    && rm /tmp/*.zip

WORKDIR /src
COPY android ./android

RUN printf 'sdk.dir=%s\n' "${ANDROID_HOME}" > android/local.properties \
    && chmod +x android/gradlew \
    && cd android && ./gradlew assembleDebug --no-daemon
