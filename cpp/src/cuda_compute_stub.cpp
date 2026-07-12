#include "cuda_compute.hpp"

#include <stdexcept>

namespace magic_geo::detail {
namespace {

[[noreturn]] void throw_cuda_not_compiled() {
    throw std::runtime_error(
        "CUDA backend is unavailable because this build was compiled without CUDA support"
    );
}

}  // namespace

struct CudaComputeSession::Impl {
    explicit Impl(int requested_device_ordinal) {
        (void)requested_device_ordinal;
        telemetry.compiled = false;
        telemetry.runtime_initialized = false;
        telemetry.available = false;
        telemetry.selected_device_ordinal = -1;
        telemetry.error =
            "CUDA support was not compiled into the native library";
    }

    CudaTelemetry telemetry;
};

CudaComputeSession::CudaComputeSession(int requested_device_ordinal)
    : impl_(new Impl(requested_device_ordinal)) {}

CudaComputeSession::~CudaComputeSession() {
    delete impl_;
}

CudaTelemetry CudaComputeSession::probe(int requested_device_ordinal) {
    CudaComputeSession session(requested_device_ordinal);
    return session.telemetry();
}

bool CudaComputeSession::available() const noexcept {
    return impl_ != nullptr && impl_->telemetry.available;
}

const CudaTelemetry& CudaComputeSession::telemetry() const noexcept {
    return impl_->telemetry;
}

void CudaComputeSession::run_assign_plates(
    const std::vector<Vec3>&,
    const std::vector<Cell>&,
    std::vector<int>&
) {
    throw_cuda_not_compiled();
}

void CudaComputeSession::run_smooth_field(
    const std::vector<Cell>&,
    const std::vector<double>&,
    int,
    double,
    std::vector<double>&
) {
    throw_cuda_not_compiled();
}

void CudaComputeSession::run_smooth_three_fields(
    const std::vector<Cell>&,
    const std::vector<double>&,
    const std::vector<double>&,
    const std::vector<double>&,
    int,
    double,
    double,
    double,
    std::vector<double>&,
    std::vector<double>&,
    std::vector<double>&
) {
    throw_cuda_not_compiled();
}

void CudaComputeSession::run_remap_crust_sources(
    const std::vector<Cell>&,
    const std::vector<Vec3>&,
    const std::vector<std::vector<int>>&,
    std::vector<int>&
) {
    throw_cuda_not_compiled();
}

void CudaComputeSession::run_crust_overlap_continuous_shadow(
    const CrustTransportPlan&,
    const std::vector<Cell>&,
    const std::vector<double>&,
    const std::vector<double>&,
    const std::vector<double>&,
    CrustOverlapContinuousShadowResult&
) {
    throw_cuda_not_compiled();
}

}  // namespace magic_geo::detail
