#include "layered_ice_forcing_history.hpp"

#include <stdexcept>
#include <utility>

namespace magic_geo::detail {

struct LayeredIceForcingHistory::Node {
    std::shared_ptr<const Node> left, right;
    std::shared_ptr<const LayeredIceOwnerForcing> value;
};

const LayeredIceForcingHistory::Node& LayeredIceForcingHistory::leaf(
    const std::shared_ptr<const Node>& root,std::size_t capacity,std::size_t index
) {
    auto node=root.get();
    while(capacity>1 && node) {
        capacity/=2;
        if(index<capacity) node=node->left.get();
        else { index-=capacity; node=node->right.get(); }
    }
    if(!node || !node->value) throw std::out_of_range("forcing history index");
    return *node;
}

std::shared_ptr<const LayeredIceForcingHistory::Node> LayeredIceForcingHistory::append_node(
    const std::shared_ptr<const Node>& old,std::size_t capacity,std::size_t index,
    std::shared_ptr<const LayeredIceOwnerForcing> value
) {
    Node node;
    if(old) node=*old;
    if(capacity==1) node.value=std::move(value);
    else {
        const auto half=capacity/2;
        if(index<half) node.left=append_node(node.left,half,index,std::move(value));
        else node.right=append_node(node.right,half,index-half,std::move(value));
    }
    return std::make_shared<const Node>(std::move(node));
}

LayeredIceForcingHistory::LayeredIceForcingHistory(std::vector<LayeredIceOwnerForcing> values) {
    if(values.size()>maximum_records) throw std::length_error("forcing history record cap");
    for(auto& value:values) *this=appended(std::move(value));
}

LayeredIceForcingHistory::LayeredIceForcingHistory(LayeredIceForcingHistory&& other) noexcept
    :root_(std::move(other.root_)),size_(std::exchange(other.size_,0)),
     capacity_(std::exchange(other.capacity_,1)),stored_values_(std::exchange(other.stored_values_,0)) {}

LayeredIceForcingHistory& LayeredIceForcingHistory::operator=(LayeredIceForcingHistory&& other) noexcept {
    if(this!=&other) {
        root_=std::move(other.root_);size_=std::exchange(other.size_,0);
        capacity_=std::exchange(other.capacity_,1);stored_values_=std::exchange(other.stored_values_,0);
    }
    return *this;
}

const LayeredIceOwnerForcing& LayeredIceForcingHistory::operator[](std::size_t index) const {
    if(index>=size_) throw std::out_of_range("forcing history index");
    return *leaf(root_,capacity_,index).value;
}

LayeredIceForcingHistory LayeredIceForcingHistory::appended(LayeredIceOwnerForcing value) const {
    if(size_>=maximum_records) throw std::length_error("forcing history record cap");
    if(value.absorbed_shortwave_w_m2.size()>maximum_values-stored_values_)
        throw std::length_error("forcing history value cap");
    auto next=*this;
    if(size_==capacity_) {
        next.root_=std::make_shared<const Node>(Node{root_,{}, {}});
        next.capacity_*=2;
    }
    next.stored_values_+=value.absorbed_shortwave_w_m2.size();
    next.root_=append_node(next.root_,next.capacity_,size_,
        std::make_shared<const LayeredIceOwnerForcing>(std::move(value)));
    ++next.size_;
    return next;
}

bool LayeredIceForcingHistory::has_prefix(const LayeredIceForcingHistory& prefix) const {
    if(prefix.size_>size_) return false;
    if(root_==prefix.root_ && size_==prefix.size_) return true;
    for(std::size_t i=0;i<prefix.size_;++i)
        if(leaf(root_,capacity_,i).value!=leaf(prefix.root_,prefix.capacity_,i).value) return false;
    return true;
}

LayeredIceForcingHistory::const_iterator::const_iterator(const LayeredIceForcingHistory& h,std::size_t i)
    :root_(h.root_),capacity_(h.capacity_),size_(h.size_),index_(i) {}

LayeredIceForcingHistory::const_iterator::reference LayeredIceForcingHistory::const_iterator::operator*() const {
    if(index_>=size_) throw std::out_of_range("forcing history iterator");
    return *LayeredIceForcingHistory::leaf(root_,capacity_,index_).value;
}

} // namespace magic_geo::detail
