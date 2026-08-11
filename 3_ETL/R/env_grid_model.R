# -*- coding: utf-8 -*-
# env_grid_model.R — 관찰 추천도 모델이 쓰는 환경 격자를 만든다.
#
# env_layers.R 이 내는 env_grid.csv 에는 bio01·bio06·bio12·dem·ndvi·ndwi 만 있고,
# 모델 변수 6개 중 bio03·bio14·bio18 이 없다. 그 셋만 추가로 뽑아 붙인다.
# env_grid.csv 를 고치지 않고 옆에 새 파일을 만드는 이유는, 이미 배포된 env_grid.js 가
# 그 파일에서 파생되기 때문이다 — 컬럼을 늘리면 전 종 자산이 함께 흔들린다.
#
# 값은 배포 정밀도로 반올림해 저장한다(model_config.R 의 SCALE). 브라우저는 env_grid.js 의
# 정수 스케일 값을 되돌려 쓰므로, 모델이 원시 정밀도로 학습하면 학습한 값과 예측에 쓰는 값이
# 달라진다. 차이는 작지만 굳이 남길 이유가 없고, 남기면 나중에 원인 찾기 어려운 불일치가 된다.
#
# 좌표는 env_grid.csv 의 lon/lat 을 그대로 쓴다 → 셀 정렬이 정의상 일치한다.
# 산출 : 1_Data/processed/env_grid_model.csv  (cid, lon, lat, dem, ndvi, bio01, bio18, bio03, bio14)
# 실행 : Rscript -e "source('3_ETL/R/env_grid_model.R')"   (공백경로 직접실행은 exit 127)
suppressMessages({library(terra); library(data.table)})

BASE <- "D:/Google_Drive/Finding gap"
PROC <- file.path(BASE, "1_Data", "processed")
BIO  <- "D:/Google_Drive/Paper/Lucanidae/Data/Zonal/bioclim"
source(file.path(BASE, "3_ETL", "R", "model_config.R"))

SRC <- file.path(PROC, "env_grid.csv")
OUT <- file.path(PROC, "env_grid_model.csv")
ADD <- c("bio03", "bio14", "bio18")

if (file.exists(OUT) && file.mtime(OUT) > file.mtime(SRC)) {
  cat("env_grid_model.csv 가 env_grid.csv 보다 최신 — 건너뜀\n")
} else {
  g <- fread(SRC)
  d <- g[, .(cid, lon, lat, dem = as.numeric(dem),
             ndvi = as.numeric(ndvi), bio01 = as.numeric(bio01))]
  cat(sprintf("격자 %s 셀 로드\n", format(nrow(d), big.mark = ",")))

  pts <- vect(cbind(d$lon, d$lat), crs = "EPSG:4326")
  for (v in ADD) {
    r <- rast(file.path(BIO, paste0(v, ".tif")))
    d[[v]] <- terra::extract(r, project(pts, crs(r)))[, 2]
    rm(r); gc(verbose = FALSE)
    cat(sprintf("  %s 추출 · 결측 %s\n", v, format(sum(is.na(d[[v]])), big.mark = ",")))
    flush.console()
  }

  # 배포 정밀도로 고정 — 브라우저가 되돌려 쓸 값과 동일하게 만든다
  for (v in V) d[[v]] <- round(d[[v]] * SCALE[[v]]) / SCALE[[v]]

  setcolorder(d, c("cid", "lon", "lat", V))
  fwrite(d, OUT)
  cat(sprintf("\n저장 %s · 완전관측 %s / %s 셀 · 정밀도 %s\n", basename(OUT),
              format(sum(complete.cases(d[, ..V])), big.mark = ","),
              format(nrow(d), big.mark = ","),
              paste(sprintf("%s/%g", V, SCALE[V]), collapse = " ")))
}
