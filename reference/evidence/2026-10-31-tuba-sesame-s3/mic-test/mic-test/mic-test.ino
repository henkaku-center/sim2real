// Mic bench test: AE-MICAMP OUT on GPIO5 (VCC 3V3). Streams 16 kHz 16-bit mono
// to the laptop over USB serial in frames: 0xA5 0x5A + 256 little-endian samples.
// Reflash the robot firmware afterwards (calibration in NVS is not touched).
#include <esp_adc/adc_continuous.h>

constexpr uint32_t RATE = 16000, OVERSAMPLE = 1;   // 4x oversampling measured noisier (2026-11-14), so off
constexpr size_t SAMPLES = 256;
adc_continuous_handle_t adc;

void setup() {
  pinMode(7, INPUT);   // robot board: leave hub OE to its pull-up (servo outputs disabled)
  Serial.setTxBufferSize(8192);   // default 256 B is smaller than one 514 B frame
  Serial.begin(921600);
  Serial.setTxTimeoutMs(0);
  adc_continuous_handle_cfg_t handle = {};
  handle.max_store_buf_size = 8 * OVERSAMPLE * SAMPLES * SOC_ADC_DIGI_RESULT_BYTES;
  handle.conv_frame_size = OVERSAMPLE * SAMPLES * SOC_ADC_DIGI_RESULT_BYTES;
  adc_continuous_new_handle(&handle, &adc);
  adc_digi_pattern_config_t pattern = {};
  pattern.atten = ADC_ATTEN_DB_12; pattern.channel = ADC_CHANNEL_4;   // GPIO5
  pattern.unit = ADC_UNIT_1; pattern.bit_width = SOC_ADC_DIGI_MAX_BITWIDTH;
  adc_continuous_config_t config = {};
  config.pattern_num = 1; config.adc_pattern = &pattern; config.sample_freq_hz = RATE * OVERSAMPLE;
  config.conv_mode = ADC_CONV_SINGLE_UNIT_1; config.format = ADC_DIGI_OUTPUT_FORMAT_TYPE2;
  adc_continuous_config(adc, &config);
  adc_continuous_start(adc);
}

void loop() {
  static uint8_t raw[OVERSAMPLE * SAMPLES * SOC_ADC_DIGI_RESULT_BYTES];
  static uint8_t frame[2 + SAMPLES * 2] = {0xA5, 0x5A};
  static float dc = 2048;
  uint32_t got = 0;
  if (adc_continuous_read(adc, raw, sizeof(raw), &got, 100) != ESP_OK) return;
  size_t n = 0;
  constexpr uint32_t STEP = OVERSAMPLE * SOC_ADC_DIGI_RESULT_BYTES;
  for (uint32_t i = 0; i + STEP <= got && n < SAMPLES; i += STEP) {
    float v = 0;
    for (uint32_t k = 0; k < OVERSAMPLE; ++k)
      v += reinterpret_cast<const adc_digi_output_data_t*>(raw + i + k * SOC_ADC_DIGI_RESULT_BYTES)->type2.data;
    v /= OVERSAMPLE;
    dc += (v - dc) * (1.0f / 2048);                       // remove the VCC/2 bias
    const int16_t s = int16_t(constrain((v - dc) * 16, -32767.0f, 32767.0f));
    frame[2 + 2 * n] = s & 0xFF; frame[3 + 2 * n] = s >> 8; ++n;
  }
  if (n == SAMPLES && Serial.availableForWrite() >= int(sizeof(frame))) Serial.write(frame, sizeof(frame));
}
