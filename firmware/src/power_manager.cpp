#include "stealth_mesh.h"
#include <Arduino.h>

void PowerManager::begin() {
    pinMode(StealthPins::LED_PIN, OUTPUT);
    digitalWrite(StealthPins::LED_PIN, HIGH); // LED off (active LOW on SuperMini)
}

void PowerManager::enterLightDutyCycle(RadioDriver& radio, uint32_t sleep_ms) {
    radio.sleep();
    delay(sleep_ms);
    radio.startReceive();
}
