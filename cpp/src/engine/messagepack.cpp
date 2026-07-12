#include "messagepack.hpp"

#include <bit>
#include <charconv>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

namespace magic_geo::detail {
namespace {

constexpr std::size_t MAX_JSON_NESTING_DEPTH = 256;

bool is_utf8_continuation(unsigned char value) {
    return (value & 0xc0U) == 0x80U;
}

std::size_t utf8_sequence_length(std::string_view value, std::size_t offset) {
    const auto first = static_cast<unsigned char>(value[offset]);
    const std::size_t remaining = value.size() - offset;
    if (first <= 0x7f) {
        return 1;
    }
    if (first >= 0xc2 && first <= 0xdf) {
        return remaining >= 2 &&
                is_utf8_continuation(static_cast<unsigned char>(value[offset + 1]))
            ? 2
            : 0;
    }
    if (first >= 0xe0 && first <= 0xef) {
        if (remaining < 3) {
            return 0;
        }
        const auto second = static_cast<unsigned char>(value[offset + 1]);
        const auto third = static_cast<unsigned char>(value[offset + 2]);
        const bool valid_second = first == 0xe0
            ? second >= 0xa0 && second <= 0xbf
            : first == 0xed
                ? second >= 0x80 && second <= 0x9f
                : is_utf8_continuation(second);
        return valid_second && is_utf8_continuation(third) ? 3 : 0;
    }
    if (first >= 0xf0 && first <= 0xf4) {
        if (remaining < 4) {
            return 0;
        }
        const auto second = static_cast<unsigned char>(value[offset + 1]);
        const auto third = static_cast<unsigned char>(value[offset + 2]);
        const auto fourth = static_cast<unsigned char>(value[offset + 3]);
        const bool valid_second = first == 0xf0
            ? second >= 0x90 && second <= 0xbf
            : first == 0xf4
                ? second >= 0x80 && second <= 0x8f
                : is_utf8_continuation(second);
        return valid_second && is_utf8_continuation(third) &&
                is_utf8_continuation(fourth)
            ? 4
            : 0;
    }
    return 0;
}

class JsonToMessagePack {
public:
    explicit JsonToMessagePack(std::string_view input) : input_(input) {
        const std::size_t initial_capacity = input.size() > 128
            ? input.size() / 2
            : input.size();
        output_.reserve(initial_capacity);
    }

    std::vector<std::uint8_t> convert() {
        skip_whitespace();
        parse_value(0);
        skip_whitespace();
        if (position_ != input_.size()) {
            fail("trailing content after the root value");
        }
        return std::move(output_);
    }

private:
    [[noreturn]] void fail(const char* message) const {
        throw std::runtime_error(
            "invalid JSON for MessagePack at byte " +
            std::to_string(position_) + ": " + message
        );
    }

    void skip_whitespace() {
        while (position_ < input_.size()) {
            const char ch = input_[position_];
            if (ch != ' ' && ch != '\t' && ch != '\n' && ch != '\r') {
                break;
            }
            ++position_;
        }
    }

    bool consume(char expected) {
        if (position_ < input_.size() && input_[position_] == expected) {
            ++position_;
            return true;
        }
        return false;
    }

    void require(char expected, const char* message) {
        if (!consume(expected)) {
            fail(message);
        }
    }

    void parse_value(std::size_t depth) {
        if (depth > MAX_JSON_NESTING_DEPTH) {
            fail("nesting depth exceeds 256");
        }
        if (position_ >= input_.size()) {
            fail("expected a value");
        }
        switch (input_[position_]) {
            case '{':
                parse_object(depth);
                return;
            case '[':
                parse_array(depth);
                return;
            case '"':
                parse_string();
                return;
            case 't':
                parse_literal("true", 0xc3);
                return;
            case 'f':
                parse_literal("false", 0xc2);
                return;
            case 'n':
                parse_literal("null", 0xc0);
                return;
            default:
                if (input_[position_] == '-' ||
                    (input_[position_] >= '0' && input_[position_] <= '9')) {
                    parse_number();
                    return;
                }
                fail("expected a JSON value");
        }
    }

    void parse_literal(std::string_view literal, std::uint8_t marker) {
        if (input_.substr(position_, literal.size()) != literal) {
            fail("invalid literal");
        }
        position_ += literal.size();
        output_.push_back(marker);
    }

    void parse_object(std::size_t depth) {
        require('{', "expected object");
        const std::size_t header = output_.size();
        output_.push_back(0xdf);  // map32; count is back-patched below.
        append_u32(0);

        skip_whitespace();
        std::uint64_t count = 0;
        if (consume('}')) {
            patch_u32(header + 1, 0);
            return;
        }
        while (true) {
            skip_whitespace();
            if (position_ >= input_.size() || input_[position_] != '"') {
                fail("object keys must be strings");
            }
            parse_string();
            skip_whitespace();
            require(':', "expected ':' after object key");
            skip_whitespace();
            parse_value(depth + 1);
            ++count;
            if (count > std::numeric_limits<std::uint32_t>::max()) {
                fail("object contains too many entries");
            }
            skip_whitespace();
            if (consume('}')) {
                break;
            }
            require(',', "expected ',' or '}' in object");
        }
        patch_u32(header + 1, static_cast<std::uint32_t>(count));
    }

    void parse_array(std::size_t depth) {
        require('[', "expected array");
        const std::size_t header = output_.size();
        output_.push_back(0xdd);  // array32; count is back-patched below.
        append_u32(0);

        skip_whitespace();
        std::uint64_t count = 0;
        if (consume(']')) {
            patch_u32(header + 1, 0);
            return;
        }
        while (true) {
            skip_whitespace();
            parse_value(depth + 1);
            ++count;
            if (count > std::numeric_limits<std::uint32_t>::max()) {
                fail("array contains too many entries");
            }
            skip_whitespace();
            if (consume(']')) {
                break;
            }
            require(',', "expected ',' or ']' in array");
        }
        patch_u32(header + 1, static_cast<std::uint32_t>(count));
    }

    void parse_string() {
        require('"', "expected string");
        const std::size_t content_start = position_;

        // Most generated keys and values contain no escapes. In that common
        // case, validate and copy the original UTF-8 span directly.
        while (position_ < input_.size()) {
            const unsigned char ch =
                static_cast<unsigned char>(input_[position_]);
            if (ch == '"') {
                const std::string_view value = input_.substr(
                    content_start,
                    position_ - content_start
                );
                validate_utf8(value);
                ++position_;
                append_string(value);
                return;
            }
            if (ch == '\\') {
                position_ = content_start;
                parse_escaped_string();
                return;
            }
            if (ch < 0x20) {
                fail("unescaped control character in string");
            }
            ++position_;
        }
        fail("unterminated string");
    }

    void parse_escaped_string() {
        std::string decoded;
        while (position_ < input_.size()) {
            const unsigned char ch =
                static_cast<unsigned char>(input_[position_++]);
            if (ch == '"') {
                validate_utf8(decoded);
                append_string(decoded);
                return;
            }
            if (ch < 0x20) {
                fail("unescaped control character in string");
            }
            if (ch != '\\') {
                decoded.push_back(static_cast<char>(ch));
                continue;
            }
            if (position_ >= input_.size()) {
                fail("unterminated string escape");
            }
            const char escape = input_[position_++];
            switch (escape) {
                case '"': decoded.push_back('"'); break;
                case '\\': decoded.push_back('\\'); break;
                case '/': decoded.push_back('/'); break;
                case 'b': decoded.push_back('\b'); break;
                case 'f': decoded.push_back('\f'); break;
                case 'n': decoded.push_back('\n'); break;
                case 'r': decoded.push_back('\r'); break;
                case 't': decoded.push_back('\t'); break;
                case 'u': {
                    std::uint32_t code_point = parse_hex_quad();
                    if (code_point >= 0xd800 && code_point <= 0xdbff) {
                        if (position_ + 2 > input_.size() ||
                            input_[position_] != '\\' ||
                            input_[position_ + 1] != 'u') {
                            fail("high surrogate is not followed by a low surrogate");
                        }
                        position_ += 2;
                        const std::uint32_t low = parse_hex_quad();
                        if (low < 0xdc00 || low > 0xdfff) {
                            fail("high surrogate is not followed by a low surrogate");
                        }
                        code_point = 0x10000 +
                            ((code_point - 0xd800) << 10U) +
                            (low - 0xdc00);
                    } else if (code_point >= 0xdc00 && code_point <= 0xdfff) {
                        fail("unpaired low surrogate");
                    }
                    append_utf8(decoded, code_point);
                    break;
                }
                default:
                    fail("unsupported string escape");
            }
        }
        fail("unterminated string");
    }

    std::uint32_t parse_hex_quad() {
        if (position_ + 4 > input_.size()) {
            fail("truncated unicode escape");
        }
        std::uint32_t value = 0;
        for (int index = 0; index < 4; ++index) {
            const char ch = input_[position_++];
            value <<= 4U;
            if (ch >= '0' && ch <= '9') {
                value |= static_cast<std::uint32_t>(ch - '0');
            } else if (ch >= 'a' && ch <= 'f') {
                value |= static_cast<std::uint32_t>(ch - 'a' + 10);
            } else if (ch >= 'A' && ch <= 'F') {
                value |= static_cast<std::uint32_t>(ch - 'A' + 10);
            } else {
                fail("invalid unicode escape");
            }
        }
        return value;
    }

    static void append_utf8(std::string& output, std::uint32_t code_point) {
        if (code_point <= 0x7f) {
            output.push_back(static_cast<char>(code_point));
        } else if (code_point <= 0x7ff) {
            output.push_back(static_cast<char>(0xc0U | (code_point >> 6U)));
            output.push_back(static_cast<char>(0x80U | (code_point & 0x3fU)));
        } else if (code_point <= 0xffff) {
            output.push_back(static_cast<char>(0xe0U | (code_point >> 12U)));
            output.push_back(static_cast<char>(0x80U | ((code_point >> 6U) & 0x3fU)));
            output.push_back(static_cast<char>(0x80U | (code_point & 0x3fU)));
        } else {
            output.push_back(static_cast<char>(0xf0U | (code_point >> 18U)));
            output.push_back(static_cast<char>(0x80U | ((code_point >> 12U) & 0x3fU)));
            output.push_back(static_cast<char>(0x80U | ((code_point >> 6U) & 0x3fU)));
            output.push_back(static_cast<char>(0x80U | (code_point & 0x3fU)));
        }
    }

    void validate_utf8(std::string_view value) const {
        std::size_t index = 0;
        while (index < value.size()) {
            const auto first = static_cast<unsigned char>(value[index++]);
            if (first <= 0x7f) {
                continue;
            }
            std::size_t continuation_count = 0;
            std::uint32_t code_point = 0;
            std::uint32_t minimum = 0;
            if (first >= 0xc2 && first <= 0xdf) {
                continuation_count = 1;
                code_point = first & 0x1fU;
                minimum = 0x80;
            } else if (first >= 0xe0 && first <= 0xef) {
                continuation_count = 2;
                code_point = first & 0x0fU;
                minimum = 0x800;
            } else if (first >= 0xf0 && first <= 0xf4) {
                continuation_count = 3;
                code_point = first & 0x07U;
                minimum = 0x10000;
            } else {
                fail("string is not valid UTF-8");
            }
            if (index + continuation_count > value.size()) {
                fail("string is not valid UTF-8");
            }
            for (std::size_t offset = 0; offset < continuation_count; ++offset) {
                const auto next = static_cast<unsigned char>(value[index++]);
                if ((next & 0xc0U) != 0x80U) {
                    fail("string is not valid UTF-8");
                }
                code_point = (code_point << 6U) | (next & 0x3fU);
            }
            if (code_point < minimum || code_point > 0x10ffff ||
                (code_point >= 0xd800 && code_point <= 0xdfff)) {
                fail("string is not valid UTF-8");
            }
        }
    }

    void parse_number() {
        const std::size_t start = position_;
        const bool negative = consume('-');
        if (position_ >= input_.size()) {
            fail("truncated number");
        }
        if (consume('0')) {
            if (position_ < input_.size() && input_[position_] >= '0' &&
                input_[position_] <= '9') {
                fail("leading zero in number");
            }
        } else {
            if (input_[position_] < '1' || input_[position_] > '9') {
                fail("invalid integer component");
            }
            while (position_ < input_.size() && input_[position_] >= '0' &&
                input_[position_] <= '9') {
                ++position_;
            }
        }

        bool floating_point = false;
        if (consume('.')) {
            floating_point = true;
            const std::size_t fraction_start = position_;
            while (position_ < input_.size() && input_[position_] >= '0' &&
                input_[position_] <= '9') {
                ++position_;
            }
            if (position_ == fraction_start) {
                fail("fraction has no digits");
            }
        }
        if (position_ < input_.size() &&
            (input_[position_] == 'e' || input_[position_] == 'E')) {
            floating_point = true;
            ++position_;
            if (position_ < input_.size() &&
                (input_[position_] == '+' || input_[position_] == '-')) {
                ++position_;
            }
            const std::size_t exponent_start = position_;
            while (position_ < input_.size() && input_[position_] >= '0' &&
                input_[position_] <= '9') {
                ++position_;
            }
            if (position_ == exponent_start) {
                fail("exponent has no digits");
            }
        }

        const char* begin = input_.data() + start;
        const char* end = input_.data() + position_;
        if (floating_point) {
            double value = 0.0;
            const auto result = std::from_chars(
                begin,
                end,
                value,
                std::chars_format::general
            );
            if (result.ec != std::errc() || result.ptr != end ||
                !std::isfinite(value)) {
                fail("floating-point number is out of binary64 range");
            }
            output_.push_back(0xcb);
            append_u64(std::bit_cast<std::uint64_t>(value));
            return;
        }

        if (negative) {
            std::int64_t value = 0;
            const auto result = std::from_chars(begin, end, value, 10);
            if (result.ec != std::errc() || result.ptr != end) {
                fail("negative integer is out of signed 64-bit range");
            }
            append_signed(value);
        } else {
            std::uint64_t value = 0;
            const auto result = std::from_chars(begin, end, value, 10);
            if (result.ec != std::errc() || result.ptr != end) {
                fail("integer is out of unsigned 64-bit range");
            }
            append_unsigned(value);
        }
    }

    void append_string(std::string_view value) {
        if (value.size() > std::numeric_limits<std::uint32_t>::max()) {
            fail("string exceeds MessagePack's 32-bit size limit");
        }
        const auto size = static_cast<std::uint32_t>(value.size());
        if (size <= 31) {
            output_.push_back(static_cast<std::uint8_t>(0xa0U | size));
        } else if (size <= std::numeric_limits<std::uint8_t>::max()) {
            output_.push_back(0xd9);
            output_.push_back(static_cast<std::uint8_t>(size));
        } else if (size <= std::numeric_limits<std::uint16_t>::max()) {
            output_.push_back(0xda);
            append_u16(static_cast<std::uint16_t>(size));
        } else {
            output_.push_back(0xdb);
            append_u32(size);
        }
        output_.insert(output_.end(), value.begin(), value.end());
    }

    void append_unsigned(std::uint64_t value) {
        if (value <= 0x7fU) {
            output_.push_back(static_cast<std::uint8_t>(value));
        } else if (value <= std::numeric_limits<std::uint8_t>::max()) {
            output_.push_back(0xcc);
            output_.push_back(static_cast<std::uint8_t>(value));
        } else if (value <= std::numeric_limits<std::uint16_t>::max()) {
            output_.push_back(0xcd);
            append_u16(static_cast<std::uint16_t>(value));
        } else if (value <= std::numeric_limits<std::uint32_t>::max()) {
            output_.push_back(0xce);
            append_u32(static_cast<std::uint32_t>(value));
        } else {
            output_.push_back(0xcf);
            append_u64(value);
        }
    }

    void append_signed(std::int64_t value) {
        if (value >= -32) {
            output_.push_back(static_cast<std::uint8_t>(value));
        } else if (value >= std::numeric_limits<std::int8_t>::min()) {
            output_.push_back(0xd0);
            output_.push_back(static_cast<std::uint8_t>(value));
        } else if (value >= std::numeric_limits<std::int16_t>::min()) {
            output_.push_back(0xd1);
            append_u16(static_cast<std::uint16_t>(value));
        } else if (value >= std::numeric_limits<std::int32_t>::min()) {
            output_.push_back(0xd2);
            append_u32(static_cast<std::uint32_t>(value));
        } else {
            output_.push_back(0xd3);
            append_u64(static_cast<std::uint64_t>(value));
        }
    }

    void append_u16(std::uint16_t value) {
        output_.push_back(static_cast<std::uint8_t>(value >> 8U));
        output_.push_back(static_cast<std::uint8_t>(value));
    }

    void append_u32(std::uint32_t value) {
        output_.push_back(static_cast<std::uint8_t>(value >> 24U));
        output_.push_back(static_cast<std::uint8_t>(value >> 16U));
        output_.push_back(static_cast<std::uint8_t>(value >> 8U));
        output_.push_back(static_cast<std::uint8_t>(value));
    }

    void append_u64(std::uint64_t value) {
        for (int shift = 56; shift >= 0; shift -= 8) {
            output_.push_back(static_cast<std::uint8_t>(value >> shift));
        }
    }

    void patch_u32(std::size_t offset, std::uint32_t value) {
        output_[offset] = static_cast<std::uint8_t>(value >> 24U);
        output_[offset + 1] = static_cast<std::uint8_t>(value >> 16U);
        output_[offset + 2] = static_cast<std::uint8_t>(value >> 8U);
        output_[offset + 3] = static_cast<std::uint8_t>(value);
    }

    std::string_view input_;
    std::size_t position_ = 0;
    std::vector<std::uint8_t> output_;
};

}  // namespace

std::string sanitize_utf8(std::string_view value) {
    std::string sanitized;
    sanitized.reserve(value.size());
    std::size_t offset = 0;
    while (offset < value.size()) {
        const std::size_t length = utf8_sequence_length(value, offset);
        if (length == 0) {
            sanitized += "\xef\xbf\xbd";
            ++offset;
        } else {
            sanitized.append(value.substr(offset, length));
            offset += length;
        }
    }
    return sanitized;
}

std::vector<std::uint8_t> json_to_messagepack(std::string_view json) {
    return JsonToMessagePack(json).convert();
}

}  // namespace magic_geo::detail
