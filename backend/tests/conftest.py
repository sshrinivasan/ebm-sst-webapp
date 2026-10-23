"""Shared test fixtures and constants."""

# The sample Soil Analytical File's deepest sample is at 15 m, but the default
# topsoil/subsoil depth table (params.py) only extends to 12 m. The pipeline
# rejects uncovered samples (validate_topsoil_depths), so full-pipeline tests
# must pass an explicit table that covers the deepest sample.
EXTENDED_TOPSOIL_DEPTHS = [
    {"top": "0",   "bottom": "0.3", "type": "Topsoil"},
    {"top": "0.3", "bottom": "1",   "type": "Subsoil"},
    {"top": "1",   "bottom": "1.5", "type": "Subsoil"},
    {"top": "1.5", "bottom": "6",   "type": "Subsoil"},
    {"top": "6",   "bottom": "12",  "type": "Subsoil"},
    {"top": "12",  "bottom": "15",  "type": "Subsoil"},
]
