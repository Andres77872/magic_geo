#include "layered_ice_owner.hpp"
#include "layered_ice_owner_kernel.hpp"

#include <limits>
#include <mutex>
#include <utility>

namespace magic_geo::detail {
namespace {
constexpr const char* journal_prefix="{\"model\":\"lossless_layered_owner_journal_v1\",\"seed\":";
constexpr const char* journal_records=",\"records\":[";
void need(bool ok,const char* code,const char* detail) {
    if(!ok) throw LayeredIceError(code,detail);
}
void add_work(LayeredIceOwnerWork& a,const LayeredIceOwnerWork& c) {
#define ADD(n) a.n+=c.n
    ADD(graph_builds_started);ADD(material_calls_started);ADD(calorimeter_calls_started);
    ADD(remap_calls_started);ADD(thermal_calls_started);ADD(internal_be_calls_started);ADD(scalar_evaluations);
    ADD(absorption_calls_started);
    ADD(topology_calls_started);
#undef ADD
    a.observed_counts_complete=a.observed_counts_complete && c.observed_counts_complete;
}
// Wire-byte accounting deliberately excludes allocator capacity, computation
// scratch and caller-made copies. Its lifetime follows the returned payload.
struct Retention {
    std::mutex mutex;
    std::size_t history_bytes=0,history_reserved=0,private_bytes=0,private_count=0;
};
struct Lease {
    std::shared_ptr<Retention> accounting;
    std::size_t bytes=0,journal_reservation=0;
    bool committed=false;
    explicit Lease(std::shared_ptr<Retention> a):accounting(std::move(a)){}
    ~Lease() {
        std::lock_guard lock(accounting->mutex);
        if(!committed && bytes) {accounting->private_bytes-=bytes;--accounting->private_count;}
        accounting->history_reserved-=journal_reservation;
    }
    void resize(std::size_t exact_bytes) {
        need(exact_bytes<=bytes,"receipt_cap","payload exceeds its private reservation");
        std::lock_guard lock(accounting->mutex);
        accounting->private_bytes-=bytes-exact_bytes;bytes=exact_bytes;
        if(journal_reservation) {
            const auto next=exact_bytes+1;
            accounting->history_reserved-=journal_reservation-next;journal_reservation=next;
        }
    }
    void discard_journal_reservation() {
        std::lock_guard lock(accounting->mutex);
        accounting->history_reserved-=journal_reservation;journal_reservation=0;
    }
    void commit(std::size_t wire_bytes) noexcept {
        std::lock_guard lock(accounting->mutex);
        accounting->private_bytes-=bytes;--accounting->private_count;
        accounting->history_reserved-=journal_reservation;journal_reservation=0;
        accounting->history_bytes+=wire_bytes;committed=true;
    }
};
struct Payload {
    std::shared_ptr<Lease> lease;
    LayeredIceOwnerReceipt receipt;
};
struct Record {
    std::string id,key,encoded;
    std::shared_ptr<const LayeredIceOwnerReceipt> receipt;
    std::shared_ptr<Lease> lease;
};
} // namespace
struct LayeredIceOwner::Impl {
    mutable std::mutex mutex;
    std::shared_ptr<const int> anchor=std::make_shared<const int>(0);
    std::shared_ptr<const LayeredIceOwnerSnapshot> accepted;
    std::vector<std::shared_ptr<const Record>> records;
    std::string journal_seed;
    std::shared_ptr<Retention> retention=std::make_shared<Retention>();
    std::vector<std::shared_ptr<const LayeredIceOwnerReceipt>> minimal_refusals;
    LayeredIceOwnerLimits limits;
    double budget=0;
    LayeredIceOwnerWork meter;
    std::size_t in_flight=0;
    std::shared_ptr<const LayeredIceOwnerReceipt> minimal(const char* code,bool metered=true) const {
        for(const auto& r:minimal_refusals)
            if(r->failure_code==code && r->work.prepare_attempts==(metered?1U:0U)) return r;
        throw std::logic_error("missing bounded minimal receipt");
    }
};
struct LayeredIceOwnerCandidate::Data {
    std::shared_ptr<const int> owner;
    std::shared_ptr<const LayeredIceOwnerSnapshot> base;
    std::shared_ptr<const Record> record;
};
LayeredIceOwnerCandidate::LayeredIceOwnerCandidate(std::shared_ptr<const Data> p):data_(std::move(p)){}
const LayeredIceOwnerReceipt& LayeredIceOwnerCandidate::receipt()const{return *data_->record->receipt;}
LayeredIceOwner::LayeredIceOwner(LayeredIceOwnerSeed seed,double budget,LayeredIceOwnerLimits limits):impl_(std::make_unique<Impl>()) {
    impl_->accepted=layered_ice_owner_kernel::initialize_snapshot(std::move(seed),budget,limits);
    impl_->journal_seed=layered_ice_owner_journal_seed_json(*impl_->accepted);
    const std::size_t framing=std::string(journal_prefix).size()+std::string(journal_records).size()+2;
    need(impl_->journal_seed.size()<=limits.max_history_bytes &&
         framing<=limits.max_history_bytes-impl_->journal_seed.size(),"history_cap","seed and journal framing exceed history allowance");
    impl_->retention->history_bytes=impl_->journal_seed.size()+framing;
    impl_->records.reserve(limits.max_commits);
    for(const char* code:{"work_cap","private_receipt_cap","retained_preparation_cap","history_cap","receipt_cap"}) {
        LayeredIceOwnerReceipt r;r.failure_code=code;r.detail="bounded minimal capacity refusal";
        r.limits=limits;r.maximum_joint_energy_error_j=budget;r.work.prepare_attempts=1;
        impl_->minimal_refusals.push_back(std::make_shared<const LayeredIceOwnerReceipt>(r));
        if(std::string(code)=="work_cap") {
            r.work.prepare_attempts=0;impl_->minimal_refusals.push_back(std::make_shared<const LayeredIceOwnerReceipt>(std::move(r)));
        }
    }
    impl_->limits=limits;impl_->budget=budget;impl_->meter.graph_builds_started=1;
}
LayeredIceOwner::~LayeredIceOwner()=default;
std::shared_ptr<const LayeredIceOwnerSnapshot> LayeredIceOwner::snapshot()const {
    std::lock_guard lock(impl_->mutex);
    return impl_->accepted;
}
std::vector<std::shared_ptr<const LayeredIceOwnerReceipt>> LayeredIceOwner::history()const {
    std::lock_guard lock(impl_->mutex);
    std::vector<std::shared_ptr<const LayeredIceOwnerReceipt>> out;
    for(const auto& x:impl_->records) out.push_back(x->receipt);
    return out;
}
LayeredIceOwnerWork LayeredIceOwner::work()const {std::lock_guard lock(impl_->mutex);return impl_->meter;}
LayeredIceOwnerStorage LayeredIceOwner::storage()const {
    std::lock_guard lock(impl_->mutex);std::lock_guard quota_lock(impl_->retention->mutex);
    const auto& a=*impl_->retention;
    return {a.history_bytes,a.history_reserved,a.private_bytes,a.private_count,impl_->in_flight};
}
std::string LayeredIceOwner::journal_json()const {
    std::lock_guard lock(impl_->mutex);
    std::string out=std::string(journal_prefix)+impl_->journal_seed+journal_records;
    bool first=true;for(const auto& record:impl_->records) {if(!first)out+=',';first=false;out+=record->encoded;}
    out+="]}";return out;
}

LayeredIceOwnerPreparation LayeredIceOwner::prepare(const LayeredIceOwnerRequest& q,
    const std::vector<Cell>& geography,std::uint64_t geographic_revision) {
    const auto& l=impl_->limits;
    LayeredIceOwnerReceipt r;
    r.limits=l;r.maximum_joint_energy_error_j=impl_->budget;
    {
        std::lock_guard lock(impl_->mutex);
        if(impl_->meter.prepare_attempts>=l.max_prepare_attempts)
            return {impl_->minimal("work_cap",false),std::nullopt,false};
        ++impl_->meter.prepare_attempts;r.work.prepare_attempts=1;
        if(impl_->in_flight>=l.max_concurrent_preparations)
            return {impl_->minimal("work_cap"),std::nullopt,false};
        ++impl_->in_flight;
    }
    std::shared_ptr<const LayeredIceOwnerSnapshot> base;
    std::shared_ptr<Lease> lease;
    std::string key;
    bool computing=true;
    // Work reservations are operational state, not accepted physical state.
    const auto release=[&]() {
        if(computing) {std::lock_guard lock(impl_->mutex);--impl_->in_flight;add_work(impl_->meter,r.work);computing=false;}
    };
    const auto acquire_private=[&]() {
        if(lease)return;
        auto fresh=std::make_shared<Lease>(impl_->retention);
        {
            std::lock_guard lock(impl_->retention->mutex);auto& a=*impl_->retention;
            need(a.private_count<l.max_retained_preparations,"retained_preparation_cap","returned preparation count cap");
            need(a.private_bytes<=l.max_private_receipt_bytes &&
                 l.max_receipt_bytes<=l.max_private_receipt_bytes-a.private_bytes,
                 "private_receipt_cap","complete private receipt reservation unavailable");
            a.private_bytes+=l.max_receipt_bytes;++a.private_count;fresh->bytes=l.max_receipt_bytes;
        }
        lease=std::move(fresh);
    };
    try {
        layered_ice_owner_kernel::validate_request_shape(q,l);key=layered_ice_owner_request_json(q);
        need(key.size()<=l.max_receipt_bytes,"receipt_cap","request exceeds retention cap");
        std::shared_ptr<const Record> previous;
        bool geographic_matches=false;
        {
            std::lock_guard lock(impl_->mutex);base=impl_->accepted;
            geographic_matches=layered_ice_owner_kernel::geographic_matches(*base,geography,geographic_revision);
            for(const auto& old:impl_->records) if(old->id==q.id) {previous=old;break;}
        }
        // Exact replay allocates no new retained payload, even when all private
        // slots are occupied. Bounded key encoding is transient computation.
        if(geographic_matches && previous && previous->key==key) {
            release();return {previous->receipt,std::nullopt,true};
        }
        acquire_private();r.request=q;r.initial=base;
        need(geographic_matches,"stale_geography","geographic source operands or epoch revision changed");
        need(!previous,"transaction_id_conflict","committed transaction ID changed operands");
        need(q.expected_revision==base->revision,"stale_revision","request source version changed");
        need(base->revision<l.max_commits && base->revision<std::numeric_limits<std::uint64_t>::max(),
             "commit_cap","committed transaction cap");
        {
            std::lock_guard lock(impl_->retention->mutex);auto& a=*impl_->retention;
            need(a.history_bytes<=l.max_history_bytes && a.history_reserved<=l.max_history_bytes-a.history_bytes &&
                 l.max_receipt_bytes<l.max_history_bytes-a.history_bytes-a.history_reserved,
                 "history_cap","complete normalized journal record reservation unavailable");
            lease->journal_reservation=l.max_receipt_bytes+1;a.history_reserved+=lease->journal_reservation;
        }
        layered_ice_owner_kernel::prepare_physical(r);
        auto encoded=layered_ice_owner_record_json(r,key);
        need(encoded.size()<=l.max_receipt_bytes,"receipt_cap","complete normalized record exceeds private reservation");
        lease->resize(encoded.size());
        auto payload=std::make_shared<const Payload>(Payload{lease,std::move(r)});
        std::shared_ptr<const LayeredIceOwnerReceipt> diagnostic{payload,&payload->receipt};
        auto record=std::make_shared<const Record>(Record{q.id,std::move(key),std::move(encoded),diagnostic,lease});
        auto data=std::make_shared<const LayeredIceOwnerCandidate::Data>(LayeredIceOwnerCandidate::Data{impl_->anchor,base,record});
        release();return {diagnostic,LayeredIceOwnerCandidate(data),false};
    } catch(const std::bad_alloc&) {release();throw;
    } catch(const LayeredIceError& e) {r.failure_code=e.code;r.detail=e.what();
    } catch(const std::exception& e) {r.failure_code="preparation_refusal";r.detail=e.what();}
    r.prepared=false;r.final.reset();
    try {
        acquire_private();lease->discard_journal_reservation();
        auto encoded=layered_ice_owner_record_json(r,key);
        if(encoded.size()>l.max_receipt_bytes) {
            const auto work=r.work;r=LayeredIceOwnerReceipt{};
            r.failure_code="receipt_cap";r.detail="unaccepted rich diagnostic exceeds retention; no state published";
            r.limits=l;r.maximum_joint_energy_error_j=impl_->budget;r.work=work;
            encoded=layered_ice_owner_record_json(r,{});
        }
        need(encoded.size()<=l.max_receipt_bytes,"receipt_cap","minimal diagnostic exceeds retention");
        lease->resize(encoded.size());
        auto payload=std::make_shared<const Payload>(Payload{lease,std::move(r)});
        std::shared_ptr<const LayeredIceOwnerReceipt> diagnostic{payload,&payload->receipt};
        release();return {diagnostic,std::nullopt,false};
    } catch(const std::bad_alloc&) {release();throw;
    } catch(const LayeredIceError& e) {
        // Capacity failure still reports actual work. This fixed-shape control
        // metadata is explicitly outside rich wire-payload accounting.
        LayeredIceOwnerReceipt minimal;minimal.failure_code=e.code;
        minimal.detail="rich payload unavailable; fixed refusal metadata only; no state published";
        minimal.limits=l;minimal.maximum_joint_energy_error_j=impl_->budget;minimal.work=r.work;
        release();return {std::make_shared<const LayeredIceOwnerReceipt>(std::move(minimal)),std::nullopt,false};
    } catch(...) {release();throw;}
}
LayeredIceOwnerCommit LayeredIceOwner::commit(const LayeredIceOwnerCandidate& candidate,
    const std::vector<Cell>& geography,std::uint64_t geographic_revision) {
    std::lock_guard lock(impl_->mutex);
    if(!candidate.data_ || candidate.data_->owner!=impl_->anchor) return {false,false,"foreign_candidate"};
    if(!layered_ice_owner_kernel::geographic_matches(*impl_->accepted,geography,geographic_revision)) return {false,false,"stale_geography"};
    const auto& last=*candidate.data_->record;
    for(const auto& old:impl_->records) if(old->id==last.id) {
        if(old->key==last.key) return {true,true,{}};
        return {false,false,"transaction_id_conflict"};
    }
    if(candidate.data_->base!=impl_->accepted) return {false,false,"stale_candidate"};
    const auto bytes=last.encoded.size()+(impl_->records.empty()?0:1);
    // All allocations, source checks and full record reservations precede
    // publication. Reserved vector capacity and shared_ptr moves do not throw.
    impl_->records.push_back(candidate.data_->record);
    impl_->accepted=last.receipt->final;
    last.lease->commit(bytes);
    return {true,false,{}};
}
} // namespace magic_geo::detail
