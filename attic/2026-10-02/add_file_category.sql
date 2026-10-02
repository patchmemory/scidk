-- Add file_category column to files table
-- Safe to run on existing DB -- idempotent via ALTER TABLE IF NOT EXISTS workaround

-- SQLite doesn't support IF NOT EXISTS on ALTER TABLE
-- so we catch the error if column already exists
ALTER TABLE files ADD COLUMN file_category TEXT;

-- Create index for fast category queries
CREATE INDEX IF NOT EXISTS idx_files_category
    ON files(scan_id, file_category);

-- Populate file_category based on extension
-- Run this UPDATE after the ALTER TABLE
UPDATE files SET file_category = CASE
    -- Instrument raw data
    WHEN file_extension IN ('.fast5','.pod5') THEN 'nanopore_raw'
    WHEN file_extension IN ('.fastq','.fq') THEN 'sequencing_reads'
    WHEN file_extension IN ('.bam','.sam','.cram') THEN 'alignment'
    WHEN file_extension IN ('.bai','.csi','.crai') THEN 'alignment_index'
    WHEN file_extension IN ('.vcf','.bcf') THEN 'variant_calls'
    WHEN file_extension IN ('.bed','.bedgraph','.bdg','.bg') THEN 'genomic_intervals'
    WHEN file_extension IN ('.gtf','.gff','.gff3') THEN 'genome_annotation'
    WHEN file_extension IN ('.fasta','.fa','.fna','.ffn') THEN 'sequence'
    WHEN file_extension IN ('.gz','.bz2','.tgz','.zip') THEN 'compressed'
    -- Microscopy/imaging
    WHEN file_extension IN ('.tif','.tiff') THEN 'image_tiff'
    WHEN file_extension IN ('.nd2') THEN 'image_nikon'
    WHEN file_extension IN ('.czi') THEN 'image_zeiss'
    WHEN file_extension IN ('.dv') THEN 'image_deltavision'
    WHEN file_extension IN ('.oif','.oib') THEN 'image_olympus'
    WHEN file_extension IN ('.svs','.ndpi','.scn') THEN 'image_wsi'
    WHEN file_extension IN ('.dcm','.dicom') THEN 'image_dicom'
    WHEN file_extension IN ('.nii') THEN 'image_nifti'
    WHEN file_extension IN ('.png','.jpg','.jpeg','.bmp','.gif') THEN 'image_export'
    -- Analysis outputs
    WHEN file_extension IN ('.rds','.rda','.rdata') THEN 'r_object'
    WHEN file_extension IN ('.h5ad','.loom') THEN 'single_cell'
    WHEN file_extension IN ('.h5','.hdf5') THEN 'hdf5'
    WHEN file_extension IN ('.pkl','.pickle') THEN 'python_object'
    WHEN file_extension IN ('.nc','.nc4') THEN 'netcdf'
    -- Tabular data
    WHEN file_extension IN ('.csv','.tsv','.txt') THEN 'tabular'
    WHEN file_extension IN ('.xlsx','.xls') THEN 'spreadsheet'
    WHEN file_extension IN ('.parquet','.feather') THEN 'columnar'
    -- Code and config
    WHEN file_extension IN ('.py','.ipynb') THEN 'python_code'
    WHEN file_extension IN ('.r','.rmd','.rnw') THEN 'r_code'
    WHEN file_extension IN ('.sh','.bash','.slurm') THEN 'shell_script'
    WHEN file_extension IN ('.yaml','.yml','.json','.toml') THEN 'config'
    WHEN file_extension IN ('.nf','.config') THEN 'nextflow_config'
    WHEN file_extension IN ('.smk','') AND name='Snakefile' THEN 'snakemake_config'
    -- Reports and documents
    WHEN file_extension IN ('.html','.htm') THEN 'report_html'
    WHEN file_extension IN ('.pdf') THEN 'report_pdf'
    WHEN file_extension IN ('.md','.rst') THEN 'documentation'
    WHEN file_extension IN ('.docx','.doc') THEN 'document'
    WHEN file_extension IN ('.pptx','.ppt') THEN 'presentation'
    WHEN file_extension IN ('.svg') THEN 'vector_graphic'
    -- System/noise
    WHEN name LIKE '.DS_Store' THEN 'macos_artifact'
    WHEN name LIKE '._%' THEN 'macos_resource_fork'
    WHEN name LIKE '._%.%' THEN 'macos_resource_fork'
    WHEN file_extension IN ('.tmp','.temp') THEN 'temporary'
    WHEN file_extension IN ('.log') THEN 'log'
    WHEN file_extension IN ('.lock') THEN 'lock_file'
    -- Null/empty extension
    WHEN file_extension IS NULL OR file_extension = '' THEN 'no_extension'
    ELSE 'other'
END
WHERE type = 'file';
