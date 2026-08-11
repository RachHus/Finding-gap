# -*- coding: utf-8 -*-
# seed_model_store.R — 1회용. 이미 적합·검증해 둔 결과를 증분 저장소 형식으로 옮긴다.
#
# model_species.R 은 저장소가 비어 있으면 전 종(8,900여 종 · 종당 적합 5회 · 약 10시간)을
# 처음부터 돌린다. 그런데 그 결과는 이미 있다. 입력이 같다는 것도 확인했다 —
# 기존 적합이 쓴 cells_*.js 의 cid 집합과 species_cells.csv 의 집합이 표본 1,327종 전부 일치.
# 그래서 지문(sig)만 새로 계산해 붙이면 재적합 없이 저장소를 세울 수 있다.
#
# 주의: 저장하는 cfg 는 지금 격자 기준이다. 기존 적합은 bio03 을 반올림 전 값으로 학습했으므로
# 미세한 차이가 있다(0.1 단위 이하). 이 차이가 무시할 만한지는 seed 직후 한 분류군을 FORCE 로
# 다시 돌려 tss_cv 를 비교해 확인한다 — 아니면 전량 재적합이 맞다.
#
# 입력 : %LOCALAPPDATA%/fg_maxnet/maxnet_<T>.json · cv_<T>.csv
#        (이 파일들을 만든 초기 스크립트 두 개는 model_species.R 로 대체되어 제거했다.
#         입력이 사라진 뒤에 저장소를 다시 세워야 하면 시드 대신 FORCE 전량 재적합이 답이다.)
# 산출 : 1_Data/processed/model_store/<T>.json
# 실행 : Rscript -e "source('3_ETL/R/seed_model_store.R')"
suppressMessages({library(data.table); library(jsonlite); library(digest)})

BASE  <- "D:/Google_Drive/Finding gap"
PROC  <- file.path(BASE, "1_Data", "processed")
STORE <- file.path(PROC, "model_store")
OLD   <- file.path(Sys.getenv("LOCALAPPDATA"), "fg_maxnet")
dir.create(STORE, showWarnings = FALSE, recursive = TRUE)
source(file.path(BASE, "3_ETL", "R", "model_config.R"))
txfile <- function(t) gsub("[^A-Za-z0-9]", "_", t)

g <- fread(file.path(PROC, "env_grid_model.csv"))
g <- g[complete.cases(g[, ..V])]
row_of <- integer(max(g$cid) + 1L); row_of[g$cid + 1L] <- seq_len(nrow(g))
cfg <- model_cfg(as.data.frame(g[, ..V]), g$cid)
cat(sprintf("격자 %s 셀 · cfg %s\n", format(nrow(g), big.mark = ","), substr(cfg, 1, 8)))

sc <- fread(file.path(PROC, "species_cells.csv"))
sc[, ktsn := as.character(ktsn)]
sig_of <- sc[, .(sig = digest(sort(unique(cid))), ncell = uniqueN(cid)), by = ktsn]
setkey(sig_of, ktsn)
cat(sprintf("species_cells %s종 지문 계산\n", format(nrow(sig_of), big.mark = ",")))

tot <- 0L; miss <- 0L
for (mf in Sys.glob(file.path(OLD, "maxnet_*.json"))) {
  tx <- sub("^maxnet_", "", tools::file_path_sans_ext(basename(mf)))
  cvf <- file.path(OLD, sprintf("cv_%s.csv", tx))
  j <- fromJSON(mf, simplifyDataFrame = FALSE)
  cv <- if (file.exists(cvf)) {
    d <- fread(cvf); d[, ktsn := as.character(ktsn)]; setkey(d, ktsn); d
  } else NULL

  sp <- list()
  for (x in j) {
    k <- as.character(x$k)
    s <- sig_of[.(k), sig, nomatch = NULL]
    if (!length(s)) { miss <- miss + 1L; next }         # species_cells 에 없는 종 → 버린다
    c1 <- if (!is.null(cv)) cv[.(k), nomatch = NULL] else NULL
    sp[[length(sp) + 1L]] <- list(
      k = k, sig = s, n = x$n, nvar = x$nv, vars = x$vars,
      beta_names = x$beta_names, betas = x$betas,
      alpha = x$alpha, entropy = x$entropy,
      varmin = x$varmin, varmax = x$varmax, fmin = x$fmin, fmax = x$fmax,
      auc_tr = x$auc,
      auc_cv = if (!is.null(c1) && nrow(c1)) c1$auc_cv[1] else NA_real_,
      tss_cv = if (!is.null(c1) && nrow(c1)) c1$tss_cv[1] else NA_real_,
      thr_cv = if (!is.null(c1) && nrow(c1)) c1$thr_cv[1] else NA_real_)
  }
  outf <- file.path(STORE, sprintf("%s.json", txfile(tx)))
  write_json(list(cfg = cfg, built = format(Sys.time(), "%Y-%m-%d %H:%M:%S"),
                  seeded = TRUE, sp = sp), outf, auto_unbox = TRUE, digits = 8)
  ntss <- sum(sapply(sp, function(x) !is.na(x$tss_cv)))
  tot <- tot + length(sp)
  cat(sprintf("[%-3s] %5d종 → %-10s (tss_cv 보유 %d)\n", tx, length(sp), basename(outf), ntss))
}
cat(sprintf("\n합계 %s종 시드 · species_cells 미존재로 제외 %d → %s\n",
            format(tot, big.mark = ","), miss, STORE))
