#!/usr/bin/env Rscript
# Convert Korean province (SIDO) shapefile to simplified GeoJSON
# Input: BND_SIDO_PG.shp (EPSG:5186, Korean grid)
# Output: sido.geojson (EPSG:4326, WGS84)

library(sf)
library(dplyr)

# Paths
shp_path <- "D:/Google_Drive/Finding gap/1_Data/spatial/BND_SIDO_PG/BND_SIDO_PG.shp"
output_dir <- "D:/Google_Drive/Finding gap/5_App/demo/data"
output_file <- file.path(output_dir, "sido.geojson")

# Create output directory if missing
if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
  cat("Created output directory:", output_dir, "\n")
}

# Read shapefile
cat("Reading shapefile...\n")
sido <- st_read(shp_path, quiet = FALSE, stringsAsFactors = FALSE)

cat("\n=== Shapefile Info ===\n")
cat("CRS:", st_crs(sido)$input, "\n")
cat("Geometry type:", st_geometry_type(sido)[1], "\n")
cat("Number of features:", nrow(sido), "\n")
cat("\nAttribute names:\n")
print(names(sido))
cat("\nFirst few rows (attributes only):\n")
print(as.data.frame(sido)[1:3, !grepl("geometry", names(sido), ignore.case = TRUE)])

# Identify the province name and code fields
# Common field names: SIDO_NM for name, SIDO_CD for code
fields <- names(sido)
cat("\n=== Field Analysis ===\n")
cat("All fields:", paste(fields, collapse = ", "), "\n")

# Try to auto-detect name and code fields
name_field <- NULL
code_field <- NULL

for (f in fields) {
  if (grepl("NM$|_NM$|NM_", f, ignore.case = TRUE) && !grepl("geometry", f, ignore.case = TRUE)) {
    name_field <- f
    cat("Detected name field:", f, "\n")
  }
  if (grepl("^CD$|_CD$|^SIDO_CD|CODE|코드", f, ignore.case = TRUE)) {
    code_field <- f
    cat("Detected code field:", f, "\n")
  }
}

if (is.null(name_field) || is.null(code_field)) {
  cat("\nWarning: Could not auto-detect all fields. Sample values:\n")
  for (f in fields) {
    if (!grepl("geometry", f, ignore.case = TRUE)) {
      cat(f, "->", paste(unique(sido[[f]])[1:2], collapse = " | "), "\n")
    }
  }
  # Fallback: assume SIDO_NM and SIDO_CD
  if ("SIDO_NM" %in% fields && "SIDO_CD" %in% fields) {
    name_field <- "SIDO_NM"
    code_field <- "SIDO_CD"
    cat("Using fallback: name_field=", name_field, ", code_field=", code_field, "\n")
  } else {
    stop("Fields not identified. Review output above.")
  }
}

# Reproject to EPSG:4326 (WGS84)
cat("\nReprojecting to EPSG:4326...\n")
sido_4326 <- st_transform(sido, crs = 4326)

# Simplify geometry using Douglas-Peucker algorithm
# Target: < 500 KB. Use dTolerance = 500m to reduce file size
cat("Simplifying geometry (Douglas-Peucker, dTolerance=500m)...\n")
sido_simple <- st_simplify(sido_4326, dTolerance = 500, preserveTopology = TRUE)

# Select and rename properties: sido (Korean name), code (province code)
cat("Preparing final features...\n")
sido_final <- sido_simple %>%
  st_drop_geometry() %>%
  as.data.frame() %>%
  select(!!name_field, !!code_field) %>%
  mutate(
    sido = as.character(!!sym(name_field)),
    code = as.character(!!sym(code_field))
  ) %>%
  select(sido, code)

# Reattach geometry and convert to proper sf object
sido_final <- st_sf(sido_final, geometry = st_geometry(sido_simple))

cat("\n=== Final Feature List ===\n")
cat("Total features:", nrow(sido_final), "\n")
print(as.data.frame(sido_final)[, c("sido", "code")])

# Write to GeoJSON (UTF-8 encoding for Korean characters)
cat("\nWriting to GeoJSON...\n")
st_write(
  sido_final,
  output_file,
  driver = "GeoJSON",
  delete_dsn = TRUE,
  quiet = FALSE,
  layer_options = c("RFC7946=YES")
)

# Check file size
file_size_kb <- file.size(output_file) / 1024
cat("\n=== Output ===\n")
cat("File:", output_file, "\n")
cat("Size:", round(file_size_kb, 1), "KB\n")

if (file_size_kb > 500) {
  cat("\nWarning: Output exceeds 500 KB. Consider further simplification.\n")
}

cat("\nConversion complete.\n")
