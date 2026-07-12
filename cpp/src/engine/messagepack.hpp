#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace magic_geo::detail {

// Preserve valid UTF-8 and replace each malformed byte with U+FFFD. This is
// used at FFI error boundaries where driver-owned diagnostics are not
// guaranteed to be well formed.
std::string sanitize_utf8(std::string_view value);

// Transcode the engine's canonical JSON document to MessagePack without
// building a second object graph. The accepted input is deliberately strict
// JSON; malformed input, non-finite/out-of-range numbers, invalid UTF-8, and
// excessive nesting fail closed with std::runtime_error.
std::vector<std::uint8_t> json_to_messagepack(std::string_view json);

}  // namespace magic_geo::detail
