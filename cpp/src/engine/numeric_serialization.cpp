#include "internal.hpp"

#include <locale>

namespace magic_geo::detail {

std::string roundtrip_num(double value) {
    if (!std::isfinite(value)) {
        throw std::runtime_error(
            "attempted to serialize a non-finite simulation value"
        );
    }
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << std::defaultfloat
        << std::setprecision(std::numeric_limits<double>::max_digits10)
        << value;
    return out.str();
}

std::string roundtrip_double_array_json(const std::vector<double>& values) {
    std::string out = "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            out += ",";
        }
        out += roundtrip_num(values[i]);
    }
    out += "]";
    return out;
}

}  // namespace magic_geo::detail
