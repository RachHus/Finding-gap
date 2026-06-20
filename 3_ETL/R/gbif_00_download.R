# ============================================================
# gbif_00_download.R
# Finding gap — GBIF 점유(occurrence) 다운로드 (관리분류군 class 기준)
#
# 목적: 종 마스터(ktsn_master.csv)의 target 관리분류군(1~11) class를 기준으로
#       대한민국 GBIF 점유자료를 분류군별 데이터세트로 내려받는다.
#
# 참고: D:/Google_Drive/Paper/Bee/2. Code/bee_00b_national_gbif.R
#   - bee는 publisher(NMK/NIBR)로 한정 → 여기서는 그 한정을 제거(전체 GBIF).
#   - iNaturalist만으로 한정하지 않음 — 시민과학 포함 전체 publisher.
#   - 단, 공간좌표 보유 레코드만(hasCoordinate=TRUE + hasGeospatialIssue=FALSE).
#
# 동작:
#   1) ktsn_master.csv → (taxon_group, class_la) 고유쌍 → GBIF classKey 해석(name_backbone),
#      캐시 4_References/gbif_class_keys.csv.
#   1.5) class 미해석(NONE/HIGHERRANK; 예: 어류 Actinopterygii, 파충류 Reptilia→Chordata 오매칭)은
#      그 class 하위 order(목) 학명을 orderKey로 폴백 해석. 캐시 4_References/gbif_order_keys.csv.
#      → taxonKey = 정상 classKey ∪ 폴백 orderKey (분류군별).
#   2) PHASE 1(게이트): TARGET_GROUP의 taxonKey들로 occ_download 제출.
#   3) PHASE 2: 다운로드 import → 품질필터 → 1_Data/raw/gbif/gbif_<group>.csv 저장
#      (EcoBank observation_agg 파이프라인이 후속 흡수: 학명→KTSN 매칭·시도 join·연도).
#
# 자격증명(절대 하드코딩·커밋 금지): ~/.Renviron 에
#   GBIF_USER=...  GBIF_PWD=...  GBIF_EMAIL=...
# 를 넣고 R 재시작. (Finding gap 비밀정책: 키는 .env/.Renviron, git 제외)
#
# 출력:
#   4_References/gbif_class_keys.csv        — 분류군·class·GBIF key·해석상태
#   4_References/gbif_order_keys.csv        — class 미해석분의 order(목) 폴백 key·해석상태
#   1_Data/raw/gbif/gbif_<group>_key.txt    — 제출된 download key(분류군별)
#   1_Data/raw/gbif/gbif_<group>.csv        — 품질필터 통과 점유자료(좌표 포함)
# ============================================================

suppressPackageStartupMessages({
  library(rgbif); library(dplyr); library(stringr); library(readr); library(tidyr)
})

cat("=== gbif_00: Finding gap GBIF 다운로드 (class 기준) ===\n\n")

# ── 경로 ────────────────────────────────────────────────────────────────────────
BASE       <- "D:/Google_Drive/Finding gap"
MASTER     <- file.path(BASE, "1_Data/processed/ktsn_master.csv")
KEYS_CACHE <- file.path(BASE, "4_References/gbif_class_keys.csv")
GBIF_RAW   <- file.path(BASE, "1_Data/raw/gbif")
dir.create(GBIF_RAW, recursive = TRUE, showWarnings = FALSE)

# ── 설정 ────────────────────────────────────────────────────────────────────────
# 관리분류군 1~11 코드(ktsn_master.taxon_group). 데모=포유류(MM). 전체 서비스 대비 11개 모두 지원.
TARGET_GROUPS <- c("MM", "AV", "RP", "AM", "-P", "UC", "CC", "IV", "IN", "VP", "MS")
TARGET_GROUP  <- "MM"        # ← PHASE 1에서 제출할 분류군(한 번에 하나씩; 11개 순차 제출)
YEAR_MIN      <- 1900        # 전 기간(서비스 목적). 필요 시 상향.
COORD_UNCERT_MAX <- 5000     # m. NA 허용. 국가조사 ±수 km 흔함.

GBIF_USER  <- Sys.getenv("GBIF_USER")
GBIF_PWD   <- Sys.getenv("GBIF_PWD")
GBIF_EMAIL <- Sys.getenv("GBIF_EMAIL")

# ===========================================================================
# STEP 0: 마스터 → (분류군, class) → GBIF classKey 해석 (캐시)
# ===========================================================================
resolve_class_keys <- function() {
  if (file.exists(KEYS_CACHE)) {
    cat("classKey 캐시 사용:", KEYS_CACHE, "\n")
    return(read_csv(KEYS_CACHE, show_col_types = FALSE))
  }
  cat("classKey 해석(name_backbone)…\n")
  master <- read_csv(MASTER, show_col_types = FALSE)
  pairs <- master %>%
    filter(taxon_group %in% TARGET_GROUPS, !is.na(class_la), class_la != "") %>%
    distinct(taxon_group, class_la) %>%
    arrange(taxon_group, class_la)

  resolved <- pairs %>%
    rowwise() %>%
    mutate(bb = list(tryCatch(
      name_backbone(name = class_la, rank = "class", kingdom = NULL),
      error = function(e) NULL))) %>%
    mutate(
      gbif_key   = ifelse(!is.null(bb) && !is.null(bb$usageKey), bb$usageKey, NA_integer_),
      gbif_rank  = ifelse(!is.null(bb) && !is.null(bb$rank),     bb$rank,     NA_character_),
      gbif_match = ifelse(!is.null(bb) && !is.null(bb$matchType), bb$matchType, "NONE"),
      gbif_canon = ifelse(!is.null(bb) && !is.null(bb$canonicalName), bb$canonicalName, NA_character_)
    ) %>%
    select(-bb) %>%
    ungroup()

  write_csv(resolved, KEYS_CACHE)
  cat("저장:", KEYS_CACHE, "  (", nrow(resolved), "개 class)\n")
  bad <- resolved %>% filter(is.na(gbif_key) | gbif_match == "NONE")
  if (nrow(bad) > 0) {
    cat("⚠ 미해석 class(수기 확인 필요):\n"); print(bad %>% select(taxon_group, class_la, gbif_match))
  }
  resolved
}

class_keys <- resolve_class_keys()

# ===========================================================================
# STEP 0.5: class 미해석(NONE/HIGHERRANK) → 그 class 하위 order(목) 학명을 orderKey로 폴백
#   배경: name_backbone(rank="class")가 일부 class를 못 풂.
#     · -P Actinopterygii·Chondrichthyes·Petromyzontida (NONE) ← 어류 대부분이 여기
#     · RP Reptilia (HIGHERRANK → 상위 Chordata key로 잘못 매칭; 그대로 쓰면 전체 척삭동물 다운로드)
#     · IV Adenophorea·Enoplea·Thecostraca 등 · MS/VP 일부
#   해결: 해당 분류군의 KTSN order(목) 학명을 GBIF orderKey로 해석해 taxonKey 폴백.
#   캐시: 4_References/gbif_order_keys.csv
# ===========================================================================
ORDER_CACHE <- file.path(BASE, "4_References/gbif_order_keys.csv")
BAD_MATCH   <- c("NONE", "HIGHERRANK")   # 미해석 또는 상위랭크 오매칭 = 폴백 대상

bad_class_pairs <- function() {
  class_keys %>%
    filter(is.na(gbif_key) | gbif_match %in% BAD_MATCH) %>%
    distinct(taxon_group, class_la)
}

resolve_order_keys <- function() {
  if (file.exists(ORDER_CACHE)) {
    cat("orderKey 캐시 사용:", ORDER_CACHE, "\n")
    return(read_csv(ORDER_CACHE, show_col_types = FALSE))
  }
  cols <- c("taxon_group", "class_la", "order_la", "gbif_key", "gbif_rank", "gbif_match", "gbif_canon")
  bad <- bad_class_pairs()
  if (nrow(bad) == 0) {
    cat("미해석 class 없음 — order 폴백 불필요.\n")
    write_csv(setNames(data.frame(matrix(ncol = length(cols), nrow = 0)), cols), ORDER_CACHE)
    return(read_csv(ORDER_CACHE, show_col_types = FALSE))
  }
  cat("미해석 class", nrow(bad), "건 → 하위 order(목) 학명 해석(name_backbone, rank=order)…\n")
  master <- read_csv(MASTER, show_col_types = FALSE)
  orders <- master %>%
    filter(taxon_group %in% TARGET_GROUPS, !is.na(order_la), order_la != "") %>%
    distinct(taxon_group, class_la, order_la) %>%
    semi_join(bad, by = c("taxon_group", "class_la")) %>%       # 실패 class 하위 order만
    arrange(taxon_group, class_la, order_la)

  resolved <- orders %>%
    rowwise() %>%
    mutate(bb = list(tryCatch(
      name_backbone(name = order_la, rank = "order", kingdom = NULL),
      error = function(e) NULL))) %>%
    mutate(
      gbif_key   = ifelse(!is.null(bb) && !is.null(bb$usageKey),     bb$usageKey,     NA_integer_),
      gbif_rank  = ifelse(!is.null(bb) && !is.null(bb$rank),         bb$rank,         NA_character_),
      gbif_match = ifelse(!is.null(bb) && !is.null(bb$matchType),    bb$matchType,    "NONE"),
      gbif_canon = ifelse(!is.null(bb) && !is.null(bb$canonicalName), bb$canonicalName, NA_character_)
    ) %>%
    select(-bb) %>%
    ungroup()

  write_csv(resolved, ORDER_CACHE)
  cat("저장:", ORDER_CACHE, "  (", nrow(resolved), "개 order)\n")
  bad2 <- resolved %>% filter(is.na(gbif_key) | gbif_match %in% BAD_MATCH)
  if (nrow(bad2) > 0) {
    cat("⚠ order 폴백도 미해석(수기 확인 필요):\n")
    print(bad2 %>% select(taxon_group, class_la, order_la, gbif_match))
  }
  resolved
}

order_keys <- resolve_order_keys()

# taxonKey = (정상 해석 classKey) ∪ (미해석 class 하위 orderKey 폴백)
group_taxon_keys <- function(group) {
  ck <- class_keys %>%
    filter(taxon_group == group, !is.na(gbif_key), !(gbif_match %in% BAD_MATCH)) %>%
    pull(gbif_key) %>% unique()
  ok <- order_keys %>%
    filter(taxon_group == group, !is.na(gbif_key), !(gbif_match %in% BAD_MATCH)) %>%
    pull(gbif_key) %>% unique()
  keys <- unique(c(ck, ok))
  if (length(keys) == 0)
    stop(sprintf("'%s' 분류군의 GBIF taxonKey가 없음 — class/order 캐시 확인", group))
  cat(sprintf("  taxonKey(%s): class %d + order(폴백) %d = 합 %d개\n",
              group, length(ck), length(ok), length(keys)))
  keys
}

# ===========================================================================
# PHASE 1: GBIF 다운로드 제출 (분류군별)
#   술어: country=KR + taxonKey∈class키 + hasCoordinate + !geoIssue + PRESENT
#         + fossil/living/material_citation(문헌인용) 제외 = 관측·표본 유지. (publisher 무한정 = 전체 GBIF)
# ===========================================================================
SUBMIT_NEW_DOWNLOAD <- FALSE   # ← TRUE로 바꿔 제출, 끝나면 다시 FALSE

if (SUBMIT_NEW_DOWNLOAD) {
  if (GBIF_USER == "" || GBIF_PWD == "" || GBIF_EMAIL == "")
    stop("GBIF 자격증명 미설정 — ~/.Renviron 에 GBIF_USER/GBIF_PWD/GBIF_EMAIL 설정 후 R 재시작")

  keys <- group_taxon_keys(TARGET_GROUP)
  cat(sprintf("제출: group=%s | classKey=%s\n", TARGET_GROUP, paste(keys, collapse = ",")))

  dl <- occ_download(
    type = "and",
    pred("country", "KR"),
    pred_in("taxonKey", keys),          # target 분류군의 class들
    pred("hasCoordinate", TRUE),        # 공간좌표 보유만
    pred("hasGeospatialIssue", FALSE),
    pred("occurrenceStatus", "PRESENT"),
    pred_not(pred_in("basisOfRecord",
                     c("FOSSIL_SPECIMEN", "LIVING_SPECIMEN", "MATERIAL_CITATION"))),
    pred_gte("year", YEAR_MIN),
    user = GBIF_USER, pwd = GBIF_PWD, email = GBIF_EMAIL, curlopts = list()
  )

  keyfile <- file.path(GBIF_RAW, sprintf("gbif_%s_key.txt", TARGET_GROUP))
  writeLines(as.character(dl), keyfile)
  cat("\nKey:\n"); print(dl)
  cat(sprintf("\n저장: %s\n상태확인: occ_download_meta(\"%s\")\n", keyfile, as.character(dl)))
  cat("완료(SUCCEEDED)되면 SUBMIT_NEW_DOWNLOAD<-FALSE 후 PHASE 2 실행.\n")
  stop("PHASE 1 완료 — 다운로드 준비될 때까지 대기.")
}

# ===========================================================================
# PHASE 2: import → 품질필터 → CSV 저장 (분류군별)
# ===========================================================================
keyfile <- file.path(GBIF_RAW, sprintf("gbif_%s_key.txt", TARGET_GROUP))
if (!file.exists(keyfile))
  stop(sprintf("download key 없음: %s — PHASE 1 먼저 실행", keyfile))
DOWNLOAD_KEY <- trimws(readLines(keyfile, warn = FALSE)[1])

cat(sprintf("PHASE 2: group=%s key=%s\n", TARGET_GROUP, DOWNLOAD_KEY))
meta <- occ_download_meta(DOWNLOAD_KEY)
cat(sprintf("  상태=%s | 레코드=%s\n", meta$status, meta$totalRecords))
if (meta$status != "SUCCEEDED")
  stop(sprintf("아직 준비 안 됨(%s). occ_download_meta(\"%s\")", meta$status, DOWNLOAD_KEY))

cat("\nimport…\n")
gbif_raw <- occ_download_get(DOWNLOAD_KEY, path = GBIF_RAW, overwrite = TRUE) %>%
  occ_download_import()
cat(sprintf("  raw: %d 레코드\n", nrow(gbif_raw)))

# 품질필터: 좌표·종명·연도. 좌표불확실성 과대 제외(NA 허용).
n0 <- nrow(gbif_raw)
gbif_clean <- gbif_raw %>%
  filter(
    !is.na(decimalLongitude), !is.na(decimalLatitude),
    !is.na(species), species != "",
    is.na(year) | (year >= YEAR_MIN),
    is.na(coordinateUncertaintyInMeters) | coordinateUncertaintyInMeters <= COORD_UNCERT_MAX
  ) %>%
  transmute(
    gbifID, species, scientificName,
    vernacularName = coalesce(vernacularName, ""),
    class, order, family, genus,
    year, eventDate,
    decimalLongitude, decimalLatitude,
    coordinateUncertaintyInMeters,
    basisOfRecord, datasetKey, publishingOrgKey,
    institutionCode, samplingProtocol,
    taxon_group = TARGET_GROUP
  ) %>%
  distinct(species, eventDate, decimalLongitude, decimalLatitude, .keep_all = TRUE)
cat(sprintf("  필터: %d → %d (제외 %d, dedup 포함)\n", n0, nrow(gbif_clean), n0 - nrow(gbif_clean)))

out <- file.path(GBIF_RAW, sprintf("gbif_%s.csv", TARGET_GROUP))
write_csv(gbif_clean, out)
cat(sprintf("\n저장: %s\n", out))

cat(sprintf("  종수=%d | 연도 %s~%s | publisher(상위)\n",
            n_distinct(gbif_clean$species),
            suppressWarnings(min(gbif_clean$year, na.rm = TRUE)),
            suppressWarnings(max(gbif_clean$year, na.rm = TRUE))))
print(sort(table(gbif_clean$institutionCode), decreasing = TRUE)[1:10])

cat("\n=== gbif_00 완료 ===\n")
cat("다음: 분류군별 PHASE1/2 반복(TARGET_GROUP 변경) → Python 어댑터로 observation_agg 흡수\n")
cat("인용: occ_download_meta()$doi 로 데이터셋 DOI 확보(원출처 모델).\n")
