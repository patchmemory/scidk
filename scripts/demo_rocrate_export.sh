#!/usr/bin/env bash
# SciDK Demo: Scan → Browse → Select → Create RO-Crate → ZIP Export
#
# Usage:
#   ./scripts/demo_rocrate_export.sh [SOURCE_PATH] [OUTPUT_ZIP]
#
# Example:
#   ./scripts/demo_rocrate_export.sh ~/Documents/my-project ./my-crate.zip
#
# Prerequisites:
#   - SciDK server running at http://127.0.0.1:5000 (or set SCIDK_URL)
#   - jq installed (for JSON parsing)
#   - curl installed

set -euo pipefail

# Configuration
SCIDK_URL="${SCIDK_URL:-http://127.0.0.1:5000}"
SOURCE_PATH="${1:-}"
OUTPUT_ZIP="${2:-./demo-crate.zip}"
TEMP_DIR=$(mktemp -d)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

cleanup() {
    log_info "Cleaning up temporary directory: ${TEMP_DIR}"
    rm -rf "${TEMP_DIR}"
}

trap cleanup EXIT

check_dependencies() {
    local missing=()

    if ! command -v curl &> /dev/null; then
        missing+=("curl")
    fi

    if ! command -v jq &> /dev/null; then
        missing+=("jq")
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required dependencies: ${missing[*]}"
        log_info "Install with: brew install ${missing[*]}  # macOS"
        log_info "         or: sudo apt install ${missing[*]}  # Debian/Ubuntu"
        exit 1
    fi
}

check_server() {
    log_info "Checking SciDK server at ${SCIDK_URL}..."

    if ! curl -sf "${SCIDK_URL}/api/health" &> /dev/null; then
        log_error "SciDK server not responding at ${SCIDK_URL}"
        log_info "Start the server with: scidk-serve"
        log_info "Or set SCIDK_URL to your server address"
        exit 1
    fi

    log_success "Server is running"
}

# Main workflow steps

step1_scan() {
    local path="$1"

    log_info "Step 1: Scanning directory ${path}..."

    if [ ! -d "${path}" ]; then
        log_error "Directory does not exist: ${path}"
        exit 1
    fi

    # Trigger scan via API
    local response
    response=$(curl -sf -X POST "${SCIDK_URL}/api/scan" \
        -H "Content-Type: application/json" \
        -d "{\"path\": \"${path}\", \"recursive\": true}" || echo "{}")

    if [ -z "${response}" ] || ! echo "${response}" | jq -e '.scan_id' &> /dev/null; then
        log_error "Scan failed. Response: ${response}"
        exit 1
    fi

    local scan_id
    scan_id=$(echo "${response}" | jq -r '.scan_id')
    local file_count
    file_count=$(echo "${response}" | jq -r '.scanned // 0')

    log_success "Scan completed: scan_id=${scan_id}, files=${file_count}"
    echo "${scan_id}"
}

step2_browse() {
    local scan_id="$1"

    log_info "Step 2: Browsing scanned datasets..."

    # Get datasets from scan
    local datasets
    datasets=$(curl -sf "${SCIDK_URL}/api/datasets" || echo "[]")

    local count
    count=$(echo "${datasets}" | jq 'length')

    log_success "Found ${count} datasets"

    # Show sample (first 5)
    if [ "${count}" -gt 0 ]; then
        log_info "Sample datasets:"
        echo "${datasets}" | jq -r '.[:5] | .[] | "  - \(.filename) (\(.extension))"'
    fi

    echo "${datasets}"
}

step3_select() {
    local datasets="$1"

    log_info "Step 3: Selecting files for RO-Crate..."

    # For demo, select all Python, CSV, and JSON files
    local selected
    selected=$(echo "${datasets}" | jq '[.[] | select(.extension == "py" or .extension == "csv" or .extension == "json" or .extension == "md")]')

    local count
    count=$(echo "${selected}" | jq 'length')

    log_success "Selected ${count} files for RO-Crate"

    if [ "${count}" -gt 0 ]; then
        log_info "Selected file types:"
        echo "${selected}" | jq -r 'group_by(.extension) | .[] | "\(.length) x .\(.[0].extension)"'
    fi

    echo "${selected}"
}

step4_create_crate() {
    local source_path="$1"
    local crate_dir="${TEMP_DIR}/crate"

    log_info "Step 4: Creating RO-Crate metadata..."

    mkdir -p "${crate_dir}"

    # Generate ro-crate-metadata.json via API
    local metadata_response
    metadata_response=$(curl -sf "${SCIDK_URL}/api/rocrate?path=${source_path}" 2>/dev/null || echo '{}')

    if [ "$(echo "${metadata_response}" | jq -e 'has("@context")')" != "true" ]; then
        log_warning "RO-Crate API not available or returned error"
        log_info "Generating minimal RO-Crate metadata manually..."

        # Fallback: create minimal valid RO-Crate metadata
        cat > "${crate_dir}/ro-crate-metadata.json" <<EOF
{
  "@context": "https://w3id.org/ro/crate/1.1/context",
  "@graph": [
    {
      "@type": "CreativeWork",
      "@id": "ro-crate-metadata.json",
      "conformsTo": {
        "@id": "https://w3id.org/ro/crate/1.1"
      },
      "about": {
        "@id": "./"
      }
    },
    {
      "@type": "Dataset",
      "@id": "./",
      "name": "SciDK Demo Crate",
      "description": "Research Object Crate created by SciDK demo script",
      "datePublished": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
      "license": {
        "@id": "https://spdx.org/licenses/CC-BY-4.0"
      },
      "hasPart": []
    }
  ]
}
EOF
    else
        echo "${metadata_response}" | jq '.' > "${crate_dir}/ro-crate-metadata.json"
    fi

    log_success "RO-Crate metadata created at ${crate_dir}/ro-crate-metadata.json"

    # Copy data files
    log_info "Copying data files to crate..."

    if [ -d "${source_path}" ]; then
        cp -r "${source_path}"/* "${crate_dir}/" 2>/dev/null || log_warning "Some files may not have been copied"
        log_success "Data files copied to crate"
    else
        log_warning "Source path is not a directory; skipping file copy"
    fi

    echo "${crate_dir}"
}

step5_export_zip() {
    local crate_dir="$1"
    local output_zip="$2"

    log_info "Step 5: Exporting RO-Crate as ZIP..."

    # Ensure output directory exists
    local output_dir
    output_dir=$(dirname "${output_zip}")
    mkdir -p "${output_dir}"

    # Create ZIP
    (cd "${crate_dir}" && zip -r - .) > "${output_zip}"

    local zip_size
    zip_size=$(du -h "${output_zip}" | cut -f1)

    log_success "RO-Crate exported to ${output_zip} (${zip_size})"
}

verify_crate() {
    local output_zip="$1"

    log_info "Verifying RO-Crate package..."

    # Check ZIP contents
    if command -v unzip &> /dev/null; then
        log_info "ZIP contents:"
        unzip -l "${output_zip}" | head -20
    fi

    # Check for required metadata file
    if unzip -l "${output_zip}" | grep -q "ro-crate-metadata.json"; then
        log_success "✓ ro-crate-metadata.json present"
    else
        log_error "✗ ro-crate-metadata.json missing"
        return 1
    fi

    # Extract and validate JSON structure
    local temp_json="${TEMP_DIR}/metadata.json"
    unzip -p "${output_zip}" ro-crate-metadata.json > "${temp_json}" 2>/dev/null

    if jq -e '.["@context"]' "${temp_json}" &> /dev/null; then
        log_success "✓ Valid JSON-LD with @context"
    else
        log_warning "✗ Missing or invalid @context"
    fi

    if jq -e '.["@graph"]' "${temp_json}" &> /dev/null; then
        log_success "✓ @graph present"
    else
        log_warning "✗ Missing @graph"
    fi

    log_success "RO-Crate verification complete"
}

print_summary() {
    local output_zip="$1"

    cat <<EOF

${GREEN}════════════════════════════════════════════════════════════${NC}
${GREEN}                  DEMO COMPLETE! 🎉                         ${NC}
${GREEN}════════════════════════════════════════════════════════════${NC}

Your RO-Crate package is ready:
  📦 ${output_zip}

Workflow completed:
  ✓ Scan directory
  ✓ Browse datasets
  ✓ Select files
  ✓ Create RO-Crate metadata
  ✓ Export as ZIP

Next steps:
  • Inspect: unzip -l ${output_zip}
  • Validate: cat ro-crate-metadata.json | jq '.'
  • Share: Upload to repository or send to collaborators

For more information:
  • Full docs: README.md
  • RO-Crate spec: https://www.researchobject.org/ro-crate/
  • SciDK UI: ${SCIDK_URL}

EOF
}

# Main execution
main() {
    echo ""
    log_info "SciDK RO-Crate Demo Script"
    log_info "============================"
    echo ""

    # Validate arguments
    if [ -z "${SOURCE_PATH}" ]; then
        log_error "Usage: $0 <source-path> [output-zip]"
        log_info "Example: $0 ~/Documents/my-project ./my-crate.zip"
        exit 1
    fi

    # Convert to absolute path
    SOURCE_PATH=$(cd "${SOURCE_PATH}" && pwd)

    log_info "Source: ${SOURCE_PATH}"
    log_info "Output: ${OUTPUT_ZIP}"
    echo ""

    # Pre-flight checks
    check_dependencies
    check_server
    echo ""

    # Execute workflow
    local scan_id
    scan_id=$(step1_scan "${SOURCE_PATH}")
    echo ""

    local datasets
    datasets=$(step2_browse "${scan_id}")
    echo ""

    local selected
    selected=$(step3_select "${datasets}")
    echo ""

    local crate_dir
    crate_dir=$(step4_create_crate "${SOURCE_PATH}")
    echo ""

    step5_export_zip "${crate_dir}" "${OUTPUT_ZIP}"
    echo ""

    verify_crate "${OUTPUT_ZIP}"
    echo ""

    print_summary "${OUTPUT_ZIP}"
}

main "$@"
