/**
 * @file pulseq.h
 * @brief The raw Pulseq file model the conversion is fed, and its shape codec.
 *
 * This module is self-contained: it depends on no other library in this
 * repository. It owns the model (pulseq_types.h), the accessors that resolve
 * a block's content ids and its extension chain, and the run-length shape
 * codec the intermediate representation keeps its waveforms in.
 */

#ifndef PULSEQ_H
#define PULSEQ_H

#include <stdio.h>

#include "pulseq_config.h"
#include "pulseq_types.h"

#if defined(__cplusplus) && !defined(PULSEQ_NO_EXTERN_C)
extern "C"
{
#endif

    /* ============================================================== */
    /*  Lifecycle                                                     */
    /* ============================================================== */

    /**
     * @brief Zero-initialize a pulseq_file before reading into it.
     * @param[out] seq     File to initialize.
     * @param[in]  raster  Design-time rasters, used only for the ones the
     *                     .seq file's [DEFINITIONS] section omits; the file's
     *                     own declared rasters always win.  NULL leaves them
     *                     zero.  These are NOT system/hardware rasters -- see
     *                     pulseq_raster.
     */
    void pulseq_file_init(pulseq_file *seq, const pulseq_raster *raster);

    /** @brief Release everything a file holds and leave it initialised. */
    void pulseq_file_free(pulseq_file *seq);

    /* ============================================================== */
    /*  Block accessors                                               */
    /* ============================================================== */

    /**
     * @brief Resolve a block's raw content ids (rf/gx/gy/gz/adc/extension
     * chain head) from the BLOCKS table, without inlining event data.
     */
    int pulseq_get_raw_block_content_ids(
        const pulseq_file *seq,
        pulseq_raw_block *block,
        int block_index,
        int parse_extensions);

    /** @brief Walk a block's extension chain into a resolved index set. */
    void pulseq_get_raw_extension(
        const pulseq_file *seq,
        pulseq_raw_extension *ext,
        const pulseq_raw_block *raw);

    /* ============================================================== */
    /*  Shape codec                                                   */
    /* ============================================================== */

    /**
     * @brief Decompress a run-length-encoded SHAPES library entry.
     * @param[out] result   Receives the decompressed samples (caller frees
     *                      result->samples with PULSEQ_FREE).
     * @param[in]  encoded  Raw (possibly RLE-compressed) shape.
     * @param[in]  scale    Multiplier applied to every decompressed sample.
     * @return 1 on success, 0 on failure.
     */
    int pulseq_decompress_shape(
        pulseq_shape *result,
        const pulseq_shape *encoded,
        PULSEQ_REAL scale);

#if defined(__cplusplus) && !defined(PULSEQ_NO_EXTERN_C)
}
#endif

#endif /* PULSEQ_H */
