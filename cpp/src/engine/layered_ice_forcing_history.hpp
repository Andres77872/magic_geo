#pragma once

#include <cstddef>
#include <iterator>
#include <memory>
#include <string>
#include <vector>

namespace magic_geo::detail {

struct LayeredIceOwnerForcing {
    std::string id;
    double begin_seconds = 0, end_seconds = 0;
    // Geographic Cell-ID order, including when local columns are permuted.
    std::vector<double> absorbed_shortwave_w_m2;
};

// Immutable bounded append-only values. Every prefix retains shared tree
// nodes; appending copies O(log K) small nodes and stores the new forcing
// vector once. It performs no clock/physics validation or model execution.
class LayeredIceForcingHistory {
    struct Node;
    std::shared_ptr<const Node> root_;
    std::size_t size_ = 0, capacity_ = 1, stored_values_ = 0;
    static const Node& leaf(const std::shared_ptr<const Node>&,std::size_t,std::size_t);
    static std::shared_ptr<const Node> append_node(const std::shared_ptr<const Node>&,
        std::size_t,std::size_t,std::shared_ptr<const LayeredIceOwnerForcing>);
public:
    static constexpr std::size_t maximum_records = 2048;
    static constexpr std::size_t maximum_values = 2097152;
    LayeredIceForcingHistory() = default;
    LayeredIceForcingHistory(const LayeredIceForcingHistory&) = default;
    LayeredIceForcingHistory& operator=(const LayeredIceForcingHistory&) = default;
    LayeredIceForcingHistory(LayeredIceForcingHistory&&) noexcept;
    LayeredIceForcingHistory& operator=(LayeredIceForcingHistory&&) noexcept;
    explicit LayeredIceForcingHistory(std::vector<LayeredIceOwnerForcing>);
    std::size_t size() const noexcept { return size_; }
    bool empty() const noexcept { return size_ == 0; }
    std::size_t stored_values() const noexcept { return stored_values_; }
    const LayeredIceOwnerForcing& operator[](std::size_t) const;
    LayeredIceForcingHistory appended(LayeredIceOwnerForcing) const;
    // Identity of existing immutable entries, not merely equal numeric data.
    bool has_prefix(const LayeredIceForcingHistory&) const;

    class const_iterator {
        std::shared_ptr<const Node> root_;
        std::size_t capacity_ = 1, size_ = 0, index_ = 0;
        const_iterator(const LayeredIceForcingHistory&,std::size_t);
        friend class LayeredIceForcingHistory;
    public:
        using iterator_category = std::forward_iterator_tag;
        using value_type = LayeredIceOwnerForcing;
        using difference_type = std::ptrdiff_t;
        using pointer = const value_type*;
        using reference = const value_type&;
        const_iterator() = default;
        reference operator*() const;
        pointer operator->() const { return &**this; }
        const_iterator& operator++() { ++index_; return *this; }
        const_iterator operator++(int) { auto old=*this; ++*this; return old; }
        bool operator==(const const_iterator& other) const {
            return root_==other.root_ && size_==other.size_ && index_==other.index_;
        }
    };
    const_iterator begin() const { return {*this,0}; }
    const_iterator end() const { return {*this,size_}; }
};

} // namespace magic_geo::detail
