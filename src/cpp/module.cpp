/**
 * @file module.cpp
 * @brief The compiled extension, bound as `pulserver._ext`.
 */

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <cstddef>
#include <cstring>
#include <filesystem>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>

#include "ir/from_libraries.hpp"
#include "pulseg.h"
#include "pulseg_cache.h"
#include "pulseg_convert.h"
#include "pulseq.h"

namespace py = pybind11;

namespace
{

struct CollectionFree
{
    void operator()(pulseg_collection *coll) const { pulseg_collection_free(coll); }
};

using Collection = std::unique_ptr<pulseg_collection, CollectionFree>;

pulseg_opts make_opts(
    float gamma_hz_per_t,
    float b0_t,
    float max_grad_hz_per_m,
    float max_slew_hz_per_m_per_s,
    float rf_raster_us,
    float grad_raster_us,
    float adc_raster_us,
    float block_raster_us,
    int vendor,
    const std::array<int, 3> &label_column_map,
    const std::string &cache_ext)
{
    pulseg_opts opts;
    std::memset(&opts, 0, sizeof(opts));
    pulseg_opts_init(
        &opts,
        gamma_hz_per_t,
        b0_t,
        max_grad_hz_per_m,
        max_slew_hz_per_m_per_s,
        rf_raster_us,
        grad_raster_us,
        adc_raster_us,
        block_raster_us);
    if (cache_ext.size() >= sizeof(opts.cache_ext))
        throw std::invalid_argument("cache extension '" + cache_ext + "' is too long");
    std::memcpy(opts.cache_ext, cache_ext.c_str(), cache_ext.size() + 1);
    opts.vendor = vendor;
    for (std::size_t i = 0; i < label_column_map.size(); ++i)
        opts.label_column_map[i] = label_column_map[i];
    return opts;
}

[[noreturn]] void raise_failure(int code, const pulseg_diagnostic &diag)
{
    char message[1024];
    pulseg_format_error(message, sizeof(message), code, &diag);
    throw std::invalid_argument(std::string(message) + " [error " + std::to_string(code) + "]");
}

void require(int code, const char *what)
{
    if (PULSEG_FAILED(code))
        throw std::invalid_argument(std::string(what) + " failed: error " + std::to_string(code));
}

/* The TRID-labelled groups of one subsequence, in first-seen order. */
py::list tr_groups(const pulseg_collection *coll, int subseq_idx)
{
    pulseg_tr_group *groups = NULL;
    const int count = pulseg_get_tr_groups(coll, &groups, subseq_idx);
    if (count < 0)
    {
        if (groups)
            PULSEG_FREE(groups);
        require(count, "TR groups");
    }
    py::list out;
    for (int i = 0; i < count; ++i)
    {
        py::dict entry;
        entry["trid"] = groups[i].trid;
        entry["num_instances"] = groups[i].num_instances;
        entry["one_instance_duration_us"] = groups[i].one_instance_duration_us;
        entry["total_duration_us"] = groups[i].total_duration_us;
        out.append(entry);
    }
    if (groups)
        PULSEG_FREE(groups);
    return out;
}

py::dict summarize(const pulseg_collection *coll)
{
    pulseg_collection_info info = PULSEG_COLLECTION_INFO_INIT;
    require(pulseg_get_collection_info(coll, &info), "collection info");

    py::list subsequences;
    for (int i = 0; i < info.num_subsequences; ++i)
    {
        pulseg_subseq_info s = PULSEG_SUBSEQ_INFO_INIT;
        require(pulseg_get_subseq_info(coll, &s, i), "subsequence info");
        py::dict entry;
        entry["tr_duration_us"] = s.tr_duration_us;
        entry["num_trs"] = s.num_trs;
        entry["tr_size"] = s.tr_size;
        entry["num_unique_adcs"] = s.num_unique_adcs;
        entry["num_unique_rf"] = s.num_unique_rf;
        entry["num_canonical_trs"] = s.num_canonical_trs;
        entry["num_tr_instances"] = s.num_tr_instances;
        entry["tr_groups"] = tr_groups(coll, i);
        subsequences.append(entry);
    }

    py::list segments;
    for (int i = 0; i < info.num_segments; ++i)
    {
        pulseg_segment_info g = PULSEG_SEGMENT_INFO_INIT;
        require(pulseg_get_segment_info(coll, &g, i), "segment info");
        py::dict entry;
        entry["duration_us"] = g.duration_us;
        entry["num_blocks"] = g.num_blocks;
        entry["start_block"] = g.start_block;
        entry["pure_delay"] = g.pure_delay;
        entry["has_trigger"] = g.has_trigger;
        entry["is_nav"] = g.is_nav;
        entry["rf_adc_gap_us"] = g.rf_adc_gap_us;
        entry["adc_adc_gap_us"] = g.adc_adc_gap_us;
        segments.append(entry);
    }

    py::dict result;
    result["num_subsequences"] = info.num_subsequences;
    result["num_segments"] = info.num_segments;
    result["max_adc_samples"] = info.max_adc_samples;
    result["total_readouts"] = info.total_readouts;
    result["total_duration_us"] = info.total_duration_us;
    result["subsequences"] = subsequences;
    result["segments"] = segments;
    return result;
}

/* ------ The parsed file's own libraries, for comparison ------ */

/* An (rows, width) array of doubles, copied out of a C row array. */
py::array_t<double> rows(const PULSEQ_REAL *data, int count, int width)
{
    py::array_t<double> out({count, width});
    auto view = out.mutable_unchecked<2>();
    for (int i = 0; i < count; ++i)
        for (int j = 0; j < width; ++j)
            view(i, j) = static_cast<double>(data[(std::size_t)i * width + j]);
    return out;
}

py::array_t<int> column(const int *data, int count)
{
    py::array_t<int> out(count);
    auto view = out.mutable_unchecked<1>();
    for (int i = 0; i < count; ++i)
        view(i) = data ? data[i] : 0;
    return out;
}

py::dict libraries(const pulseq_file &seq)
{
    py::dict out;
    out["blocks"] = rows(seq.block_library ? &seq.block_library[0][0] : nullptr, seq.num_blocks, 7);
    out["rf"] = rows(seq.rf_library ? &seq.rf_library[0][0] : nullptr, seq.rf_library_size, 10);
    out["rf_use"] = column(seq.rf_use_tags, seq.rf_library_size);
    out["grad"] = rows(seq.grad_library ? &seq.grad_library[0][0] : nullptr, seq.grad_library_size, 7);
    out["adc"] = rows(seq.adc_library ? &seq.adc_library[0][0] : nullptr, seq.adc_library_size, 8);
    out["extensions"] =
        rows(seq.extensions_library ? &seq.extensions_library[0][0] : nullptr,
             seq.extensions_library_size, 3);
    out["triggers"] =
        rows(seq.trigger_library ? &seq.trigger_library[0][0] : nullptr, seq.trigger_library_size, 4);
    out["rotations"] = rows(
        seq.rotation_quaternion_library ? &seq.rotation_quaternion_library[0][0] : nullptr,
        seq.rotation_library_size,
        4);
    out["labelset"] =
        rows(seq.labelset_library ? &seq.labelset_library[0][0] : nullptr, seq.labelset_library_size, 2);
    out["labelinc"] =
        rows(seq.labelinc_library ? &seq.labelinc_library[0][0] : nullptr, seq.labelinc_library_size, 2);
    out["soft_delays"] = rows(
        seq.soft_delay_library ? &seq.soft_delay_library[0][0] : nullptr, seq.soft_delay_library_size, 4);

    py::list shims;
    for (int i = 0; i < seq.rf_shim_library_size; ++i)
    {
        const pulseq_rf_shim_entry &entry = seq.rf_shim_library[i];
        std::vector<double> values;
        for (int j = 0; j < 2 * entry.num_channels; ++j)
            values.push_back(static_cast<double>(entry.values[j]));
        shims.append(values);
    }
    out["rf_shims"] = shims;

    py::list shapes;
    for (int i = 0; i < seq.shapes_library_size; ++i)
    {
        const pulseq_shape &shape = seq.shapes_library[i];
        std::vector<double> samples;
        for (int j = 0; j < shape.num_samples; ++j)
            samples.push_back(static_cast<double>(shape.samples[j]));
        shapes.append(py::make_tuple(shape.num_uncompressed_samples, samples));
    }
    out["shapes"] = shapes;

    out["extension_map"] = std::vector<int>(seq.extension_map, seq.extension_map + 8);
    out["extension_lut"] = column(seq.extension_lut, seq.extension_lut_size + 1);

    py::dict definitions;
    for (int i = 0; i < seq.num_definitions; ++i)
    {
        std::vector<std::string> values;
        for (int j = 0; j < seq.definitions_library[i].value_size; ++j)
            values.push_back(seq.definitions_library[i].value[j]);
        definitions[py::str(seq.definitions_library[i].name)] = values;
    }
    out["definitions"] = definitions;
    return out;
}

/* Per block, what the parser resolves its extension chain to: the label
 * counters, the flags, and the specification each kind points at. */
py::dict block_extensions(const pulseq_file &seq)
{
    const int count = seq.num_blocks;
    const char *labels[] = {"SLC", "SEG", "REP", "AVG", "SET", "ECO", "PHS", "LIN", "PAR", "ACQ"};
    const char *flags[] = {"TRID", "NAV", "REV", "SMS", "REF", "IMA",
                           "NOISE", "PMC", "NOROT", "NOPOS", "NOSCL", "ONCE"};
    const char *indices[] = {"rotation", "rf_shim", "trigger", "soft_delay"};

    std::vector<std::vector<int>> labelset(10, std::vector<int>(count, 0));
    std::vector<std::vector<int>> labelinc(10, std::vector<int>(count, 0));
    std::vector<std::vector<int>> flagged(12, std::vector<int>(count, 0));
    std::vector<std::vector<int>> pointed(4, std::vector<int>(count, 0));

    for (int i = 0; i < count; ++i)
    {
        pulseq_raw_block raw;
        pulseq_raw_extension ext;
        std::memset(&raw, 0, sizeof(raw));
        std::memset(&ext, 0, sizeof(ext));
        pulseq_get_raw_block_content_ids(&seq, &raw, i, 1);
        pulseq_get_raw_extension(&seq, &ext, &raw);
        const int *set = &ext.labelset.slc;
        const int *inc = &ext.labelinc.slc;
        const int *flag = &ext.flag.trid;
        const int point[4] = {
            ext.rotation_index, ext.rf_shim_index, ext.trigger_index, ext.soft_delay_index};
        for (int j = 0; j < 10; ++j)
        {
            labelset[j][i] = set[j];
            labelinc[j][i] = inc[j];
        }
        for (int j = 0; j < 12; ++j)
            flagged[j][i] = flag[j];
        for (int j = 0; j < 4; ++j)
            pointed[j][i] = point[j];
    }

    py::dict out;
    py::dict sets, incs, bits, points;
    for (int j = 0; j < 10; ++j)
    {
        sets[labels[j]] = labelset[j];
        incs[labels[j]] = labelinc[j];
    }
    for (int j = 0; j < 12; ++j)
        bits[flags[j]] = flagged[j];
    for (int j = 0; j < 4; ++j)
        points[indices[j]] = pointed[j];
    out["labelset"] = sets;
    out["labelinc"] = incs;
    out["flags"] = bits;
    out["indices"] = points;
    return out;
}

Collection read(const std::string &seq_path, const pulseg_opts &opts, bool write_cache, bool verify_signature)
{
    pulseg_diagnostic diag = PULSEG_DIAGNOSTIC_INIT;
    pulseg_collection *raw = nullptr;
    int rc;
    {
        py::gil_scoped_release release;
        rc = pulseg_read(
            &raw, &diag, seq_path.c_str(), &opts, write_cache ? 1 : 0, verify_signature ? 1 : 0, 1);
    }
    Collection coll(raw);
    if (PULSEG_FAILED(rc))
        raise_failure(rc, diag);
    return coll;
}

} // namespace

PYBIND11_MODULE(_ext, module)
{
    module.doc() = "Compiled scanner IR conversion for pulserver";

    module.def(
        "convert",
        [](const std::string &seq_path,
           float gamma_hz_per_t,
           float b0_t,
           float max_grad_hz_per_m,
           float max_slew_hz_per_m_per_s,
           float rf_raster_us,
           float grad_raster_us,
           float adc_raster_us,
           float block_raster_us,
           int vendor,
           const std::array<int, 3> &label_column_map,
           const std::string &cache_ext,
           bool verify_signature)
        {
            const pulseg_opts opts = make_opts(
                gamma_hz_per_t,
                b0_t,
                max_grad_hz_per_m,
                max_slew_hz_per_m_per_s,
                rf_raster_us,
                grad_raster_us,
                adc_raster_us,
                block_raster_us,
                vendor,
                label_column_map,
                cache_ext);
            read(seq_path, opts, true, verify_signature);
        });

    module.def(
        "summary_from_parse",
        [](const std::string &seq_path,
           float gamma_hz_per_t,
           float b0_t,
           float max_grad_hz_per_m,
           float max_slew_hz_per_m_per_s,
           float rf_raster_us,
           float grad_raster_us,
           float adc_raster_us,
           float block_raster_us,
           const std::array<int, 3> &label_column_map)
        {
            const pulseg_opts opts = make_opts(
                gamma_hz_per_t,
                b0_t,
                max_grad_hz_per_m,
                max_slew_hz_per_m_per_s,
                rf_raster_us,
                grad_raster_us,
                adc_raster_us,
                block_raster_us,
                0,
                label_column_map,
                PULSEG_CACHE_EXT_DEFAULT);
            return summarize(read(seq_path, opts, false, false).get());
        });

    module.def(
        "chain",
        [](const std::string &first_path)
        {
            // NextSequence names are relative to the first file's directory,
            // as the converter resolves them.
            const std::filesystem::path base = std::filesystem::path(first_path).parent_path();
            std::vector<std::string> files{first_path};
            std::string current = first_path;
            for (int hop = 0; hop < 1000; ++hop)
            {
                pulseq_file file;
                pulseq_file_init(&file, nullptr);
                const int rc = pulseq_read_definitions_only(&file, current.c_str());
                const std::string next =
                    PULSEQ_FAILED(rc) ? std::string() : file.reserved_definitions_library.next_sequence;
                pulseq_file_free(&file);
                if (PULSEQ_FAILED(rc))
                    throw std::invalid_argument(
                        "cannot read the definitions of " + current + " [error " + std::to_string(rc) + "]");
                if (next.empty())
                    return files;
                current = (base / next).string();
                files.push_back(current);
            }
            throw std::invalid_argument("the NextSequence chain from " + first_path + " does not end");
        });

    module.def(
        "parse_libraries",
        [](const std::string &seq_path)
        {
            pulseq_file seq;
            pulseq_file_init(&seq, nullptr);
            const int rc = pulseq_read(&seq, seq_path.c_str());
            if (PULSEQ_FAILED(rc))
            {
                pulseq_file_free(&seq);
                throw std::invalid_argument(
                    "cannot read " + seq_path + " [error " + std::to_string(rc) + "]");
            }
            py::dict out;
            try
            {
                out = libraries(seq);
            }
            catch (...)
            {
                pulseq_file_free(&seq);
                throw;
            }
            pulseq_file_free(&seq);
            return out;
        },
        "The event, shape and definition libraries of a .seq file, as the C parser reads them.");

    module.def(
        "convert_libraries",
        [](const py::list &chain,
           const std::string &seq_path,
           float gamma_hz_per_t,
           float b0_t,
           float max_grad_hz_per_m,
           float max_slew_hz_per_m_per_s,
           float rf_raster_us,
           float grad_raster_us,
           float adc_raster_us,
           float block_raster_us,
           int vendor,
           const std::array<int, 3> &label_column_map,
           const std::string &cache_ext)
        {
            const pulseg_opts opts = make_opts(
                gamma_hz_per_t,
                b0_t,
                max_grad_hz_per_m,
                max_slew_hz_per_m_per_s,
                rf_raster_us,
                grad_raster_us,
                adc_raster_us,
                block_raster_us,
                vendor,
                label_column_map,
                cache_ext);

            const int count = static_cast<int>(chain.size());
            if (count < 1)
                throw std::invalid_argument("a chain holds at least one subsequence");
            std::vector<pulseq_file> files((size_t)count);
            for (int i = 0; i < count; ++i)
            {
                pulseq_file_init(&files[(size_t)i], nullptr);
            }
            auto release = [&files]()
            {
                for (auto &file : files)
                    pulseq_file_free(&file);
            };
            try
            {
                for (int i = 0; i < count; ++i)
                    pulserver::build_pulseq_file(
                        files[(size_t)i], chain[(size_t)i].cast<py::dict>());
            }
            catch (...)
            {
                release();
                throw;
            }

            Collection coll(pulseg_collection_alloc());
            if (!coll)
            {
                release();
                throw std::bad_alloc();
            }
            pulseg_diagnostic diag = PULSEG_DIAGNOSTIC_INIT;
            const int converted =
                pulseg_convert_collection(coll.get(), &diag, files.data(), count, &opts, 1);
            release();
            if (converted != count)
                raise_failure(diag.code, diag);
            if (PULSEG_FAILED(pulseg_save_cache(coll.get(), seq_path.c_str(), &opts)))
                throw std::invalid_argument("cannot write the cache beside " + seq_path);
        },
        "Segment a chain read into libraries and write its IR cache beside a sequence file.");

    module.def(
        "parse_block_extensions",
        [](const std::string &seq_path)
        {
            pulseq_file seq;
            pulseq_file_init(&seq, nullptr);
            const int rc = pulseq_read(&seq, seq_path.c_str());
            if (PULSEQ_FAILED(rc))
            {
                pulseq_file_free(&seq);
                throw std::invalid_argument(
                    "cannot read " + seq_path + " [error " + std::to_string(rc) + "]");
            }
            py::dict out;
            try
            {
                out = block_extensions(seq);
            }
            catch (...)
            {
                pulseq_file_free(&seq);
                throw;
            }
            pulseq_file_free(&seq);
            return out;
        },
        "Per block, the label counters, flags and specifications its extension chain names.");

    module.def(
        "summary_from_cache",
        [](const std::string &cache_path, int source_size)
        {
            Collection coll(pulseg_collection_alloc());
            if (!coll)
                throw std::bad_alloc();
            if (PULSEG_FAILED(pulseg_load_cache(coll.get(), cache_path.c_str(), source_size)))
                throw std::invalid_argument("cannot load the cache " + cache_path);
            return summarize(coll.get());
        });
}
