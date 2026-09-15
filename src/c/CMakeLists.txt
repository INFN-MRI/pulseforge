# ---------------------------------------------------------------------------
#  pulseq -- the Pulseq waveform store the IR keeps its shapes in, and the
#  RF spectrum both it and the conversion read.
#  Depends on nothing else in this repository; pulseg links it, never the
#  reverse.  Keep this target free of any pulseg include directory so the
#  one-way dependency stays enforced by the build itself.
# ---------------------------------------------------------------------------
set(PULSEQ_SOURCES
    pulseq/pulseq_shape.c
    pulseq/pulseq_rf.c
)

set(KISSFFT_SOURCES vendor/external_kiss_fft.c vendor/external_kiss_fftr.c)

# kissfft lives here rather than with pulseg because pulseq_rf.c needs it and
# pulseg links pulseq: compiling it into both would define every kissfft symbol
# twice.  pulseg keeps vendor/ on its include path for the headers.
add_library(pulseq STATIC ${PULSEQ_SOURCES} ${KISSFFT_SOURCES})
target_include_directories(pulseq PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/include/pulseq
)
target_include_directories(pulseq PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/pulseq
    ${CMAKE_CURRENT_SOURCE_DIR}/vendor
)

# ---------------------------------------------------------------------------
#  pulseg -- the vendor-neutral intermediate representation and the binary
#  cache a scanner loads it from.
# ---------------------------------------------------------------------------
set(PULSEG_SOURCES
    core/pulseg_error.c
    core/pulseg_math.c
    core/pulseg_core.c
    io/pulseg_opts.c
    io/pulseg_protocol.c
    structure/pulseg_getters.c
    structure/pulseg_descriptor.c
    cache/pulseg_cache.c
)

add_library(pulseg STATIC ${PULSEG_SOURCES})
target_link_libraries(pulseg PUBLIC pulseq)
target_include_directories(pulseg PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/include/pulseg
)
# The tree root and vendor/ hold pulseg_internal.h and the bundled kissfft:
# private, so `include/` is exactly the public API and nothing else.
target_include_directories(pulseg PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/vendor
)
