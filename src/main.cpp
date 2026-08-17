#include <Arduino.h>
#include <ETH.h>
#include <WiFiUdp.h>
#include <cstring>

#include <FastLED.h>

#if defined(OUTPUT_MODE_DMX)
  extern "C" {
    #include "driver/uart.h"
  }
#endif

// =============================================================================
// PROMETHEUS NODE FIRMWARE v0.3.2
//
// FULGUR  = Luce 1 node = Olimex ESP32-POE
// AURORA  = Luce 2 node = Wireless-Tag WT32-ETH01
//
// Safety interlock and local preview:
//   - SAFE/ARM switch is read on GPIO14 on both node types.
//   - DMX output ALWAYS boots SAFE.
//   - If the node boots while the switch is already ARM, DMX remains SAFE.
//   - The firmware must first observe a stable SAFE state, then a stable
//     SAFE->ARM transition, before DMX output is authorized.
//   - Any raw ARM->SAFE transition closes the DMX gate immediately.
//   - The six PL9823 pixels are a LOCAL PREVIEW and remain active in SAFE.
//   - Preview requires Ethernet link + fresh valid Art-Net, but NOT ARM.
//   - DMX requires ARM authorization + Ethernet link + fresh valid Art-Net.
//   - DMX mode keeps transmitting legal all-zero frames while gated.
//
// PROMETHEUS sends the same 36-channel ArtDmx frame to both nodes today:
//   channels  1..18 -> FULGUR / Luce 1 / six RGB outputs
//   channels 19..36 -> AURORA / Luce 2 / six RGB outputs
// =============================================================================

#ifndef ARTNET_UNIVERSE
#define ARTNET_UNIVERSE 0
#endif

#ifndef ARTNET_PORT
#define ARTNET_PORT 6454
#endif

#ifndef ARTNET_TIMEOUT_MS
#define ARTNET_TIMEOUT_MS 1500UL
#endif

#ifndef ARM_DEBOUNCE_MS
#define ARM_DEBOUNCE_MS 25UL
#endif

#ifndef NETWORK_RETRY_MS
#define NETWORK_RETRY_MS 2000UL
#endif

#ifndef AURORA_FADE_MS
#define AURORA_FADE_MS 250UL
#endif

static constexpr uint16_t ARTNET_OPCODE_DMX = 0x5000;
static constexpr uint16_t ARTNET_PROTOCOL_MIN = 14;
static constexpr size_t ARTNET_HEADER_SIZE = 18;
static constexpr size_t ARTNET_MAX_DMX = 512;
static constexpr uint8_t PIXEL_COUNT = 6;
static constexpr uint8_t PIXEL_CHANNELS_PER_LED = 3;
static constexpr uint8_t PIXEL_DMX_CHANNELS = PIXEL_COUNT * PIXEL_CHANNELS_PER_LED;

// Shared hardware decisions for both tabletop nodes.
static constexpr int PIXEL_DATA_PIN = 4;
static constexpr int ARM_SWITCH_PIN = 14;
static constexpr bool ARM_ACTIVE_HIGH = true;

#if defined(NODE_FULGUR)
static constexpr const char* NODE_NAME = "FULGUR";
static constexpr const char* BOARD_NAME = "Olimex ESP32-POE";
static constexpr uint8_t NODE_IP_LAST_OCTET = 10;
static constexpr uint16_t PIXEL_DMX_OFFSET = 0;
static constexpr int DMX_TX_PIN = 33;
static constexpr int DMX_DE_PIN = 32;

#elif defined(NODE_AURORA)
static constexpr const char* NODE_NAME = "AURORA";
static constexpr const char* BOARD_NAME = "Wireless-Tag WT32-ETH01";
static constexpr uint8_t NODE_IP_LAST_OCTET = 11;
static constexpr uint16_t PIXEL_DMX_OFFSET = 18;
static constexpr int DMX_TX_PIN = 17;
static constexpr int DMX_DE_PIN = 33;

#else
#error "Select NODE_FULGUR or NODE_AURORA in platformio.ini"
#endif

#if defined(OUTPUT_MODE_PIXEL) && defined(OUTPUT_MODE_DMX)
#error "Select only one output mode"
#elif !defined(OUTPUT_MODE_PIXEL) && !defined(OUTPUT_MODE_DMX)
#error "Select OUTPUT_MODE_PIXEL or OUTPUT_MODE_DMX"
#endif

static const IPAddress NODE_IP(2, 0, 0, NODE_IP_LAST_OCTET);
static const IPAddress GATEWAY_IP(2, 0, 0, 1);
static const IPAddress SUBNET_MASK(255, 0, 0, 0);

WiFiUDP artnetUdp;
uint8_t artnetBuffer[ARTNET_HEADER_SIZE + ARTNET_MAX_DMX];
uint32_t lastArtNetMs = 0;
bool ethernetStarted = false;
bool udpStarted = false;
uint32_t lastNetworkRetryMs = 0;

// SAFE/ARM state. "armAuthorized" is intentionally NOT the raw switch state.
// It only becomes true after a valid SAFE -> ARM transition since this boot.
bool armRaw = false;
bool armStable = false;
bool armStableConfirmed = false;
bool safeSeenSinceBoot = false;
bool armAuthorized = false;
uint32_t armRawChangedMs = 0;

CRGB pixels[PIXEL_COUNT];
CRGB requestedPixels[PIXEL_COUNT];

#if defined(NODE_AURORA)
CRGB auroraFadeStartPixels[PIXEL_COUNT];
uint32_t auroraFadeStartMs = 0;
#endif

#if defined(OUTPUT_MODE_DMX)
static constexpr uart_port_t DMX_UART = UART_NUM_2;
static constexpr uint32_t DMX_BAUD = 250000;
static constexpr int DMX_BREAK_BITS = 25;
uint8_t requestedDmxSlots[ARTNET_MAX_DMX] = {0};
uint8_t dmxFrame[ARTNET_MAX_DMX + 1] = {0};
#endif

static uint16_t readLE16(const uint8_t* p) {
    return static_cast<uint16_t>(p[0]) |
           (static_cast<uint16_t>(p[1]) << 8);
}

static uint16_t readBE16(const uint8_t* p) {
    return (static_cast<uint16_t>(p[0]) << 8) |
            static_cast<uint16_t>(p[1]);
}

static bool isArtNetHeader(const uint8_t* p, size_t n) {
    static const uint8_t id[8] = {'A','r','t','-','N','e','t',0x00};
    return n >= 8 && std::memcmp(p, id, 8) == 0;
}

static bool artNetFresh() {
    if (lastArtNetMs == 0) {
        return false;
    }
    return (millis() - lastArtNetMs) <= ARTNET_TIMEOUT_MS;
}

static bool previewAllowed() {
    return ETH.linkUp() && artNetFresh();
}

static bool dmxOutputAllowed() {
    return armAuthorized && previewAllowed();
}

static void printNetworkStatus() {
    Serial.printf("[%s] board=%s\n", NODE_NAME, BOARD_NAME);
    Serial.printf("[%s] IP=%s  Art-Net universe=%u  UDP=%u\n",
                  NODE_NAME,
                  ETH.localIP().toString().c_str(),
                  static_cast<unsigned>(ARTNET_UNIVERSE),
                  static_cast<unsigned>(ARTNET_PORT));
    Serial.printf("[%s] SAFE/ARM GPIO=%d active=%s debounce=%lu ms\n",
                  NODE_NAME,
                  ARM_SWITCH_PIN,
                  ARM_ACTIVE_HIGH ? "HIGH" : "LOW",
                  static_cast<unsigned long>(ARM_DEBOUNCE_MS));
    Serial.printf("[%s] local-preview=PL9823  GPIO=%d  Art-Net RGB slice=%u..%u\n",
                  NODE_NAME,
                  PIXEL_DATA_PIN,
                  static_cast<unsigned>(PIXEL_DMX_OFFSET + 1),
                  static_cast<unsigned>(PIXEL_DMX_OFFSET + PIXEL_DMX_CHANNELS));
#if defined(OUTPUT_MODE_DMX)
    Serial.printf("[%s] stage-output=DMX  TX GPIO=%d  DE GPIO=%d  512 slots @ 250k 8N2\n",
                  NODE_NAME, DMX_TX_PIN, DMX_DE_PIN);
#else
    Serial.printf("[%s] stage-output=NONE (preview-only prototype build)\n", NODE_NAME);
#endif
}

static bool startUdpListener() {
    if (udpStarted) {
        return true;
    }

    artnetUdp.stop();
    if (!artnetUdp.begin(ARTNET_PORT)) {
        Serial.printf("[%s] ERROR: UDP bind on port %u failed; retrying\n",
                      NODE_NAME, static_cast<unsigned>(ARTNET_PORT));
        return false;
    }

    udpStarted = true;
    Serial.printf("[%s] UDP listener ready on port %u\n",
                  NODE_NAME, static_cast<unsigned>(ARTNET_PORT));
    return true;
}

static void startEthernet() {
    lastNetworkRetryMs = millis();

    if (!ethernetStarted) {
        Serial.printf("[%s] starting Ethernet...\n", NODE_NAME);

        if (!ETH.begin()) {
            Serial.printf("[%s] ERROR: ETH.begin() failed; retrying\n", NODE_NAME);
            return;
        }
        ethernetStarted = true;

        delay(100);

        if (!ETH.config(NODE_IP, GATEWAY_IP, SUBNET_MASK)) {
            Serial.printf("[%s] WARNING: static IP configuration returned false\n", NODE_NAME);
        }
    }

    if (startUdpListener()) {
        printNetworkStatus();
    }
}

static void serviceNetwork() {
    if (ethernetStarted && udpStarted) {
        return;
    }
    if ((millis() - lastNetworkRetryMs) < NETWORK_RETRY_MS) {
        return;
    }
    startEthernet();
}

static uint8_t interpolateChannel(
    uint8_t start,
    uint8_t target,
    uint32_t elapsed,
    uint32_t duration
) {
    if (elapsed >= duration) {
        return target;
    }

    const int32_t delta = static_cast<int32_t>(target) - start;
    const int32_t value = static_cast<int32_t>(start) +
                          ((delta * static_cast<int32_t>(elapsed)) /
                           static_cast<int32_t>(duration));
    return static_cast<uint8_t>(value);
}

#if defined(NODE_AURORA)
static void advanceAuroraPixelFade(uint32_t now) {
    const uint32_t elapsed = now - auroraFadeStartMs;
    for (uint8_t i = 0; i < PIXEL_COUNT; ++i) {
        pixels[i] = CRGB(
            interpolateChannel(
                auroraFadeStartPixels[i].r,
                requestedPixels[i].r,
                elapsed,
                AURORA_FADE_MS
            ),
            interpolateChannel(
                auroraFadeStartPixels[i].g,
                requestedPixels[i].g,
                elapsed,
                AURORA_FADE_MS
            ),
            interpolateChannel(
                auroraFadeStartPixels[i].b,
                requestedPixels[i].b,
                elapsed,
                AURORA_FADE_MS
            )
        );
    }
}
#endif

static void blackoutPixels() {
    fill_solid(pixels, PIXEL_COUNT, CRGB::Black);
#if defined(NODE_AURORA)
    fill_solid(requestedPixels, PIXEL_COUNT, CRGB::Black);
    fill_solid(auroraFadeStartPixels, PIXEL_COUNT, CRGB::Black);
    auroraFadeStartMs = millis();
#endif
    FastLED.show();
}

static void refreshPixelPreview() {
    // Local preview is deliberately independent of SAFE/ARM.
    // In SAFE the operator can verify PROMETHEUS -> Ethernet -> Art-Net ->
    // node -> six-output color mapping without enabling stage DMX.
    if (!previewAllowed()) {
        blackoutPixels();
        return;
    }

#if defined(NODE_AURORA)
    advanceAuroraPixelFade(millis());
#else
    for (uint8_t i = 0; i < PIXEL_COUNT; ++i) {
        pixels[i] = requestedPixels[i];
    }
#endif
    FastLED.show();
}

static void setupPixelOutput() {
    FastLED.addLeds<PL9823, PIXEL_DATA_PIN, RGB>(pixels, PIXEL_COUNT);
    FastLED.setBrightness(255);
    fill_solid(requestedPixels, PIXEL_COUNT, CRGB::Black);
#if defined(NODE_AURORA)
    fill_solid(auroraFadeStartPixels, PIXEL_COUNT, CRGB::Black);
    auroraFadeStartMs = millis();
#endif
    blackoutPixels();
    Serial.printf("[%s] PL9823 local preview initialized\n", NODE_NAME);
}

static void cachePixelPayload(const uint8_t* dmx, uint16_t dmxLen) {
    CRGB newPixels[PIXEL_COUNT];
    for (uint8_t i = 0; i < PIXEL_COUNT; ++i) {
        const uint16_t base = PIXEL_DMX_OFFSET + (i * 3);
        const uint8_t r = (base + 0 < dmxLen) ? dmx[base + 0] : 0;
        const uint8_t g = (base + 1 < dmxLen) ? dmx[base + 1] : 0;
        const uint8_t b = (base + 2 < dmxLen) ? dmx[base + 2] : 0;
        newPixels[i] = CRGB(r, g, b);
    }

#if defined(NODE_AURORA)
    const uint32_t now = millis();
    advanceAuroraPixelFade(now);

    bool changed = false;
    for (uint8_t i = 0; i < PIXEL_COUNT; ++i) {
        changed = changed ||
                  newPixels[i].r != requestedPixels[i].r ||
                  newPixels[i].g != requestedPixels[i].g ||
                  newPixels[i].b != requestedPixels[i].b;
    }

    if (changed) {
        for (uint8_t i = 0; i < PIXEL_COUNT; ++i) {
            auroraFadeStartPixels[i] = pixels[i];
            requestedPixels[i] = newPixels[i];
        }
        auroraFadeStartMs = now;
    }
#else
    for (uint8_t i = 0; i < PIXEL_COUNT; ++i) {
        requestedPixels[i] = newPixels[i];
    }
#endif
}

#if defined(OUTPUT_MODE_DMX)

static void setupDmxOutput() {
    pinMode(DMX_DE_PIN, OUTPUT);
    digitalWrite(DMX_DE_PIN, HIGH);

    uart_config_t config = {};
    config.baud_rate = DMX_BAUD;
    config.data_bits = UART_DATA_8_BITS;
    config.parity = UART_PARITY_DISABLE;
    config.stop_bits = UART_STOP_BITS_2;
    config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    config.source_clk = UART_SCLK_APB;

    ESP_ERROR_CHECK(uart_param_config(DMX_UART, &config));
    ESP_ERROR_CHECK(uart_set_pin(
        DMX_UART,
        DMX_TX_PIN,
        UART_PIN_NO_CHANGE,
        UART_PIN_NO_CHANGE,
        UART_PIN_NO_CHANGE
    ));
    ESP_ERROR_CHECK(uart_driver_install(DMX_UART, 256, 0, 0, nullptr, 0));

    std::memset(requestedDmxSlots, 0, sizeof(requestedDmxSlots));
    std::memset(dmxFrame, 0, sizeof(dmxFrame));

    const uint8_t dummy = 0;
    uart_write_bytes_with_break(DMX_UART, &dummy, 1, DMX_BREAK_BITS);
    uart_wait_tx_done(DMX_UART, pdMS_TO_TICKS(100));
    delayMicroseconds(12);

    Serial.printf("[%s] DMX output initialized SAFE\n", NODE_NAME);
}

static void cacheDmxPayload(const uint8_t* dmx, uint16_t dmxLen) {
    std::memset(requestedDmxSlots, 0, sizeof(requestedDmxSlots));
    const size_t count = (dmxLen > ARTNET_MAX_DMX) ? ARTNET_MAX_DMX : dmxLen;
    if (count > 0) {
        std::memcpy(requestedDmxSlots, dmx, count);
    }
}

static void sendPhysicalDmxFrame() {
    dmxFrame[0] = 0x00;

    if (dmxOutputAllowed()) {
        std::memcpy(dmxFrame + 1, requestedDmxSlots, ARTNET_MAX_DMX);
#if defined(NODE_AURORA)
        for (uint8_t i = 0; i < PIXEL_COUNT; ++i) {
            const uint16_t base = PIXEL_DMX_OFFSET + (i * 3);
            dmxFrame[base + 1] = pixels[i].r;
            dmxFrame[base + 2] = pixels[i].g;
            dmxFrame[base + 3] = pixels[i].b;
        }
#endif
    } else {
        // SAFE, boot lockout, Ethernet loss, and Art-Net timeout all produce
        // CONTINUOUS legal zero DMX rather than disappearing DMX signal.
        std::memset(dmxFrame + 1, 0, ARTNET_MAX_DMX);
    }

    uart_write_bytes_with_break(
        DMX_UART,
        reinterpret_cast<const char*>(dmxFrame),
        sizeof(dmxFrame),
        DMX_BREAK_BITS
    );
    uart_wait_tx_done(DMX_UART, pdMS_TO_TICKS(100));
    delayMicroseconds(12);
}

#endif

static bool readArmRaw() {
    const bool high = digitalRead(ARM_SWITCH_PIN) == HIGH;
    return ARM_ACTIVE_HIGH ? high : !high;
}

static void forceSafeDmx(const char* reason) {
    // Do NOT blank the local preview here. SAFE gates stage DMX only.
    // DMX mode will transmit an all-zero frame on the same loop iteration.
    Serial.printf("[%s] %s -> DMX SAFE (local preview remains available)\n",
                  NODE_NAME, reason);
}

static void setupArmInterlock() {
    // External 10k pulldown is part of the hardware design. INPUT is used
    // deliberately so the external resistor, not an internal pull device,
    // defines the OFF/SAFE level.
    pinMode(ARM_SWITCH_PIN, INPUT);

    armRaw = readArmRaw();
    armStable = armRaw;
    armStableConfirmed = false;
    armRawChangedMs = millis();
    safeSeenSinceBoot = false;
    armAuthorized = false; // ALWAYS boot SAFE, even if switch is already ARM.

    if (armStable) {
        Serial.printf("[%s] boot switch=ARM -> LOCKED SAFE; waiting for stable input\n",
                      NODE_NAME);
    } else {
        Serial.printf("[%s] boot switch=SAFE -> confirming stable SAFE\n", NODE_NAME);
    }
}

static void serviceArmInterlock() {
    const bool now = readArmRaw();

    // Fail-safe asymmetry: any instantaneous indication of SAFE kills output
    // immediately. ARM, however, must survive debounce before authorization.
    if (!now && armAuthorized) {
        armAuthorized = false;
        forceSafeDmx("ARM->SAFE");
    }

    if (now != armRaw) {
        armRaw = now;
        armRawChangedMs = millis();
    }

    if (!armStableConfirmed) {
        if ((millis() - armRawChangedMs) < ARM_DEBOUNCE_MS) {
            return;
        }

        armStable = armRaw;
        armStableConfirmed = true;
        if (!armStable) {
            safeSeenSinceBoot = true;
            Serial.printf("[%s] boot input stable=SAFE; next SAFE->ARM may authorize\n",
                          NODE_NAME);
        } else {
            Serial.printf("[%s] boot input stable=ARM -> LOCKED SAFE; cycle through SAFE\n",
                          NODE_NAME);
        }
        return;
    }

    if (armStable == armRaw) {
        return;
    }

    if ((millis() - armRawChangedMs) < ARM_DEBOUNCE_MS) {
        return;
    }

    armStable = armRaw;

    if (!armStable) {
        safeSeenSinceBoot = true;
        armAuthorized = false;
        Serial.printf("[%s] switch stable=SAFE\n", NODE_NAME);
        return;
    }

    if (!safeSeenSinceBoot) {
        armAuthorized = false;
        Serial.printf("[%s] switch stable=ARM but SAFE not seen since boot -> LOCKED SAFE\n",
                      NODE_NAME);
        return;
    }

    armAuthorized = true;
    Serial.printf("[%s] SAFE->ARM authorized: DMX gate may open when link+Art-Net are valid\n",
                  NODE_NAME);
}

static void enforceOutputGates() {
    static bool wasPreviewAllowed = false;
    const bool previewNow = previewAllowed();
    if (previewNow != wasPreviewAllowed) {
        wasPreviewAllowed = previewNow;
        refreshPixelPreview();
        Serial.printf("[%s] local preview %s (link=%d fresh=%d)\n",
                      NODE_NAME,
                      previewNow ? "ACTIVE" : "BLACKOUT",
                      ETH.linkUp() ? 1 : 0,
                      artNetFresh() ? 1 : 0);
    }

#if defined(OUTPUT_MODE_DMX)
    static bool wasDmxAllowed = false;
    const bool dmxNow = dmxOutputAllowed();
    if (dmxNow != wasDmxAllowed) {
        wasDmxAllowed = dmxNow;
        Serial.printf("[%s] stage DMX gate %s (arm=%d link=%d fresh=%d)\n",
                      NODE_NAME,
                      dmxNow ? "OPEN" : "CLOSED/ZERO",
                      armAuthorized ? 1 : 0,
                      ETH.linkUp() ? 1 : 0,
                      artNetFresh() ? 1 : 0);
    }
#endif
}

static bool processOneArtNetPacket() {
    if (!udpStarted) {
        return false;
    }

    const int packetSize = artnetUdp.parsePacket();
    if (packetSize <= 0) {
        return false;
    }

    const size_t toRead =
        (packetSize > static_cast<int>(sizeof(artnetBuffer)))
        ? sizeof(artnetBuffer)
        : static_cast<size_t>(packetSize);

    const int bytesRead = artnetUdp.read(artnetBuffer, toRead);
    if (bytesRead < static_cast<int>(ARTNET_HEADER_SIZE)) {
        return false;
    }

    const size_t n = static_cast<size_t>(bytesRead);
    if (!isArtNetHeader(artnetBuffer, n)) {
        return false;
    }

    const uint16_t opcode = readLE16(artnetBuffer + 8);
    if (opcode != ARTNET_OPCODE_DMX) {
        return false;
    }

    const uint16_t protocolVersion = readBE16(artnetBuffer + 10);
    if (protocolVersion < ARTNET_PROTOCOL_MIN) {
        return false;
    }

    const uint16_t universe =
        static_cast<uint16_t>(artnetBuffer[14]) |
        (static_cast<uint16_t>(artnetBuffer[15] & 0x7F) << 8);
    if (universe != static_cast<uint16_t>(ARTNET_UNIVERSE)) {
        return false;
    }

    const uint16_t dmxLen = readBE16(artnetBuffer + 16);
    if (dmxLen < 2 || dmxLen > ARTNET_MAX_DMX) {
        return false;
    }
    if (ARTNET_HEADER_SIZE + dmxLen > n) {
        return false;
    }

    const uint8_t* dmx = artnetBuffer + ARTNET_HEADER_SIZE;

    cachePixelPayload(dmx, dmxLen);
#if defined(OUTPUT_MODE_DMX)
    cacheDmxPayload(dmx, dmxLen);
#endif

    lastArtNetMs = millis();
    refreshPixelPreview();

    return true;
}

void setup() {
    Serial.begin(115200);
    delay(300);

    Serial.println();
    Serial.println("==============================================");
    Serial.println(" PROMETHEUS NODE FIRMWARE v0.3.2");
    Serial.println("==============================================");

    setupPixelOutput();
#if defined(OUTPUT_MODE_DMX)
    setupDmxOutput();
#endif

    setupArmInterlock();
    startEthernet();
}

void loop() {
    serviceArmInterlock();
    serviceNetwork();

    while (processOneArtNetPacket()) {
        serviceArmInterlock();
    }

    enforceOutputGates();

#if defined(NODE_AURORA)
    if (previewAllowed()) {
        refreshPixelPreview();
    }
#endif

#if defined(OUTPUT_MODE_DMX)
    sendPhysicalDmxFrame();
#else
    delay(1);
#endif

    static uint32_t lastStatusMs = 0;
    if (millis() - lastStatusMs >= 5000) {
        lastStatusMs = millis();
        Serial.printf("[%s] link=%s ip=%s switch=%s authorized=%s fresh=%s preview=%s dmx=%s last_artnet=%lu ms\n",
                      NODE_NAME,
                      ETH.linkUp() ? "UP" : "DOWN",
                      ETH.localIP().toString().c_str(),
                      armStableConfirmed
                          ? (armStable ? "ARM" : "SAFE")
                          : "CHECK",
                      armAuthorized ? "YES" : "NO",
                      artNetFresh() ? "YES" : "NO",
                      previewAllowed() ? "ACTIVE" : "BLACK",
#if defined(OUTPUT_MODE_DMX)
                      dmxOutputAllowed() ? "LIVE" : "ZERO",
#else
                      "N/A",
#endif
                      static_cast<unsigned long>(
                          lastArtNetMs ? (millis() - lastArtNetMs) : 0
                      ));
    }
}
