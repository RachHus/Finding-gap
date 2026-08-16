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
# 하천 차수(sord)도 함께 싣는다. cell_water.csv 가 이미 칸별 Strahler 차수를 들고 있는데
# 지금까지는 "물이 있다/없다" 한 비트로만 쓰였다 — 실개천과 큰 강이 같은 값이었다는 뜻이다.
# 이 변수는 수생종에게만 배정된다(model_species.R). 육상종의 변수 구성은 그대로다.
#
# 좌표는 env_grid.csv 의 lon/lat 을 그대로 쓴다 → 셀 정렬이 정의상 일치한다.
# 산출 : 1_Data/processed/env_grid_model.csv  (cid, lon, lat, dem, ndvi, bio01, bio18, bio03, bio14, sord)
# 실행 : Rscript -e "source('3_ETL/R/env_grid_model.R')"   (공백경로 직접실행은 exit 127)
suppressMessages({library(terra); library(data.table)})

BASE <- "D:/Google_Drive/Finding gap"
PROC <- file.path(BASE, "1_Data", "processed")
BIO  <- "D:/Google_Drive/Paper/Lucanidae/Data/Zonal/bioclim"
source(file.path(BASE, "3_ETL", "R", "model_config.R"))

SRC   <- file.path(PROC, "env_grid.csv")
WATER <- file.path(PROC, "cell_water.csv")
OUT   <- file.path(PROC, "env_grid_model.csv")
ADD   <- c("bio03", "bio14", "bio18")
COLS  <- c("cid", "lon", "lat", V, "sord")

# 최신 여부를 날짜만이 아니라 컬럼 구성으로도 본다. 날짜만 보면 변수를 새로 추가했을 때
# "이미 최신"이라며 건너뛰고, 새 변수가 영영 붙지 않는다.
have  <- if (file.exists(OUT)) names(fread(OUT, nrows = 0L)) else character(0)
okV   <- all(c("cid", "lon", "lat", V) %in% have) && file.mtime(OUT) > file.mtime(SRC)
okAll <- okV && "sord" %in% have && file.mtime(OUT) > file.mtime(WATER)

if (okAll) {
  cat("env_grid_model.csv 가 원본보다 최신 — 건너뜀\n")
} else {
  if (okV) {
    # 기후 변수는 이미 현재 원본에서 나온 값이다. 차수 하나 붙이자고 bioclim 래스터를
    # 다시 훑지 않는다 — 느리기도 하지만, 값이 미세하게라도 달라지면 육상종까지 재적합된다.
    d <- fread(OUT)
    cat(sprintf("기존 격자 재사용 %s 셀 — 하천 차수만 붙인다\n", format(nrow(d), big.mark = ",")))
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
  }

  # 하천 차수 — 물길이 닿지 않는 칸은 0. 결측이 아니라 0 이어야 한다(하천이 없다는 정보다).
  w <- fread(WATER)
  d[, sord := 0L]
  d[w, on = .(cid), sord := as.integer(i.ord)]
  cat(sprintf("  하천 차수 · 물 있는 칸 %s · 최대 차수 %d\n",
              format(sum(d$sord > 0), big.mark = ","), max(d$sord)))

  setcolorder(d, COLS)
  fwrite(d, OUT)
  cat(sprintf("\n저장 %s · 완전관측 %s / %s 셀 · 정밀도 %s\n", basename(OUT),
              format(sum(complete.cases(d[, ..V])), big.mark = ","),
              format(nrow(d), big.mark = ","),
              paste(sprintf("%s/%g", V, SCALE[V]), collapse = " ")))
}
