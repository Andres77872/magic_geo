#pragma once

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <mutex>
#include <string>
#include <string_view>

namespace magic_geo::detail {

inline bool generation_progress_enabled() noexcept {
    const char* value = std::getenv("MAGIC_GEO_PROGRESS");
    return value && std::string_view(value) == "1";
}

inline void append_progress_json_string(std::string& output, std::string_view value) {
    constexpr char hex[] = "0123456789abcdef";
    output += '"';
    for (const unsigned char ch : value) {
        if (ch == '"' || ch == '\\') {
            output += '\\';
            output += static_cast<char>(ch);
        } else if (ch < 0x20) {
            output += "\\u00";
            output += hex[ch >> 4];
            output += hex[ch & 0xf];
        } else {
            output += static_cast<char>(ch);
        }
    }
    output += '"';
}

// Diagnostic-only transport: no C ABI, serialized-world or solver state changes.
// Each record is written atomically relative to other native progress records.
inline void emit_generation_progress(
    std::string_view phase, std::string_view label, std::string_view detail = {},
    std::int64_t current = -1, std::int64_t total = -1
) noexcept {
    if (!generation_progress_enabled()) return;
    try {
        std::string line = "MAGIC_GEO_PROGRESS {\"phase\":";
        append_progress_json_string(line, phase);
        line += ",\"label\":";
        append_progress_json_string(line, label);
        line += ",\"detail\":";
        append_progress_json_string(line, detail);
        if (current >= 0 && total >= 0) {
            line += ",\"current\":" + std::to_string(current);
            line += ",\"total\":" + std::to_string(total);
        }
        line += "}\n";
        static std::mutex output_mutex;
        const std::lock_guard<std::mutex> lock(output_mutex);
        std::fwrite(line.data(), 1, line.size(), stderr);
        std::fflush(stderr);
    } catch (...) {
        // Diagnostics must not make an otherwise valid simulation fail.
    }
}

// The solver may evaluate many candidate years. Report real work at most once
// per second, instead of flooding stderr for every cell or thermal substep.
class GenerationProgressCadence {
    using Clock = std::chrono::steady_clock;
    Clock::time_point last_{};
public:
    bool ready() noexcept {
        if (!generation_progress_enabled()) return false;
        const auto now = Clock::now();
        if (last_ != Clock::time_point{} && now - last_ < std::chrono::seconds(1)) return false;
        last_ = now;
        return true;
    }
};

}  // namespace magic_geo::detail
