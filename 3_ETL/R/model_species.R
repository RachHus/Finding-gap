# -*- coding: utf-8 -*-
# model_species.R — 종별 환경 적합 모델(maxnet) 증분 적합 + 교차검증.
#
# 자료가 갱신되면 전 종을 다시 적합할 이유가 없다. 새 관측이 들어온 종만 다시 돌린다.
# 판단 기준은 종별 "점유 셀 집합의 지문"이다 — species_cells.csv 에서 그 종의 cid 를 정렬해
# 해시한 값이 저장된 값과 같으면 입력이 그대로이므로 기존 모델을 그대로 쓴다.
#
# 전 종 재적합이 필요한 경우도 있다. 변수 구성·특징 종류·배경 표본 수·겹 수·구간 규칙이 바뀌거나
# 환경 격자 자체가 다시 만들어지면 모든 모델의 전제가 달라진다. 그래서 이 값들을 묶어 cfg 해시로
# 저장하고, 달라지면 저장분을 통째로 버린다. 부분만 살리면 서로 다른 전제의 모델이 한 자산에 섞인다.
#
# 모델 구성
#   변수  : A안 6개 — dem·ndvi·bio01·bio18·bio03·bio14 (전국 표본 VIF 최대 4.63)
#   구간  : 점유 셀 수에 따라 앞에서부터 자른다. 10~29→3 · 30~59→4 · 60~99→5 · 100+→6
#           A안은 중첩 구조라 변수를 줄여도 남는 변수가 바뀌지 않아 구간 간 비교가 된다.
#   수생종: ndwi_species.csv 에 오른 종은 여기에 하천 차수(sord) 하나를 더 받는다. 물속에 사는
#           종에게만 뜻이 있는 변수라 전 종에 주지 않는다 — 근거는 model_config.R 의 WVAR 주석.
#   특징  : linear + quadratic 만(classes="lq"). hinge 를 빼면 계수가 닫힌 형태로 남아
#           브라우저에서 그대로 계산되고, 표본이 얇은 구간의 과적합도 덜하다.
#   배경  : 격자 무작위 10,000 셀. 존재 셀을 배제하지 않는다 — MaxEnt 의 배경은 pseudo-absence 가
#           아니라 경관 표본이다. 존재점은 상류에서 이미 종당 1km 셀 하나로 씨닝돼 있다.
#
# 검증: 4겹 교차검증. 겹마다 존재점 3/4 로 적합하고 남긴 1/4 + 배경으로 평가한다.
#   TSS 는 임계값 의존 지표라 훈련자료에서 임계값을 고르면 그 임계값이 훈련자료에 최적화된다 —
#   held-out 없이는 값이 성립하지 않는다. max-TSS = max(민감도 + 특이도 - 1) = ROC 의 Youden J.
#   tss_cv 가 최대가 되는 지점이 그 종의 임계값(thr_cv)이고, 후보를 어디서 자를지가 여기서 정해진다.
#   신뢰 등급은 tss_cv 가 아니라 auc_cv 로 매긴다(자산 빌드 단계). 둘은 답하는 질문이 다르다 —
#   앞은 "어디서 자를까"라는 운영 결정이고, 뒤는 "이 모형이 얼마나 갈라내는가"라는 품질 진술이다.
#
# 배포 자산은 계수 묶음뿐이다. maxnet 의 predict 는 특징을 정규화하지 않고 범위로 자르기만 하므로
# 아래 값이면 예측이 정확히 재현된다(검증: 최대오차 0.00e+00):
#   link = clamp(features) %*% betas + alpha ;  cloglog = 1 - exp(-exp(entropy + link))
#
# 입력 : 1_Data/processed/species_cells.csv · env_grid_model.csv · ktsn_master.csv
# 산출 : 1_Data/processed/model_store/<TAXON>.json
# 실행 : Rscript -e "source('3_ETL/R/model_species.R')"
#        Rscript -e "FORCE<-TRUE; source('3_ETL/R/model_species.R')"   # 전량 재적합
suppressMessages({library(maxnet); library(data.table); library(jsonlite)
                  library(parallel); library(digest)})

BASE  <- "D:/Google_Drive/Finding gap"
PROC  <- file.path(BASE, "1_Data", "processed")
STORE <- file.path(PROC, "model_store")
dir.create(STORE, showWarnings = FALSE, recursive = TRUE)

source(file.path(BASE, "3_ETL", "R", "model_config.R"))
NCORE <- max(1L, min(18L, detectCores() - 2L))
if (!exists("FORCE")) FORCE <- FALSE
if (!exists("TAXA")) TAXA <- NULL          # 분류군 제한(점검·부분 재적합용). NULL 이면 전체.
txfile <- function(t) gsub("[^A-Za-z0-9]", "_", t)   # 분류군 코드 → 파일명(-P → _P)

# ── 입력 ───────────────────────────────────────────────────────────────
g0 <- fread(file.path(PROC, "env_grid_model.csv"))
g  <- g0[complete.cases(g0[, ..V])]
# 조회표는 결측 제거 '전' 최대 cid 로 잡는다. 제거 후 크기로 잡으면 그보다 큰 cid 조회가
# 범위 밖 NA 가 되고, NA > 0 은 NA 라서 아래 필터를 통과해 버린다(→ ENV[NA,] 로 적합 실패).
row_of <- integer(max(g0$cid) + 1L); row_of[g$cid + 1L] <- seq_len(nrow(g))
# 완전관측 판정은 V 로만 한다. WVAR 은 물길이 없으면 0 이라 결측이 아니고, 이걸 판정에 넣으면
# 육상 칸이 통째로 빠져 8,900종 전부의 배경이 달라진다.
ENV <- as.data.frame(g[, c(V, WVAR), with = FALSE])
rm(g0)

cfg <- model_cfg(ENV, g$cid)
cat(sprintf("격자 %s 셀 · cfg %s · 코어 %d%s\n", format(nrow(ENV), big.mark = ","),
            substr(cfg, 1, 8), NCORE, if (FORCE) " · FORCE" else ""))

sc <- fread(file.path(PROC, "species_cells.csv"))
mst <- fread(file.path(PROC, "ktsn_master.csv"), select = c("ktsn", "taxon_group"))
mst <- unique(mst[, .(ktsn = as.character(ktsn), tx = taxon_group)])
sc[, ktsn := as.character(ktsn)]
sc <- merge(sc, mst, by = "ktsn", all.x = TRUE)
sc[is.na(tx) | tx == "", tx := "NA"]

# 수생종 명단(어류 + 저서성 무척추). 서식지 후보를 수계로 자를 때 쓰는 것과 같은 파일이라
# "마스크를 받는 종"과 "차수를 배우는 종"이 어긋나지 않는다.
WET <- as.character(fread(file.path(PROC, "ndwi_species.csv"))$ktsn)
cat(sprintf("수생종 %s종 — %s 추가 배정\n", format(length(WET), big.mark = ","), WVAR))

# ── 적합 ───────────────────────────────────────────────────────────────
fit_one <- function(it) {
  k <- it$k; rows <- it$rows; n <- length(rows)
  vv <- c(V[1:nvar_for(n)], if (k %in% WET) WVAR)
  nv <- length(vv)
  tryCatch({
    # 무작위 추출은 적합 전에 한 번에 끝낸다 — 적합이 난수를 소비해도 결과가 흔들리지 않게.
    set.seed(as.integer(substr(k, nchar(k) - 8, nchar(k))) %% .Machine$integer.max)
    bg   <- sample(nrow(ENV), N_BG)
    fold <- sample(rep_len(1:KFOLD, n))

    p  <- c(rep(1, n), rep(0, N_BG))
    df <- ENV[c(rows, bg), vv, drop = FALSE]
    # 점유 셀이 아주 많은 종에서 glmnet 정규화 경로가 기본 반복수 안에 수렴하지 못하는 경우가
    # 있다. 실패로 버리기 전에 반복수를 늘려 한 번 더 시도한다.
    m <- tryCatch(maxnet(p, df, f = maxnet.formula(p, df, classes = CLASSES)),
                  error = function(e) maxnet(p, df, f = maxnet.formula(p, df, classes = CLASSES),
                                             maxit = 1e6))
    nm <- names(m$betas)
    auc_tr <- roc_stats(as.numeric(predict(m, df, type = "cloglog")), p)[1]

    ebg <- ENV[bg, vv, drop = FALSE]
    st <- matrix(NA_real_, KFOLD, 3)
    for (f in 1:KFOLD) {
      hold <- rows[fold == f]; keep <- rows[fold != f]
      if (!length(hold) || length(keep) < 3) next
      pk <- c(rep(1, length(keep)), rep(0, N_BG))
      dk <- ENV[c(keep, bg), vv, drop = FALSE]
      mk <- maxnet(pk, dk, f = maxnet.formula(pk, dk, classes = CLASSES))
      de <- rbind(ENV[hold, vv, drop = FALSE], ebg)
      st[f, ] <- roc_stats(as.numeric(predict(mk, de, type = "cloglog")),
                           c(rep(1, length(hold)), rep(0, N_BG)))
    }
    cm <- colMeans(st, na.rm = TRUE)

    list(k = k, sig = it$sig, n = n, nvar = nv, vars = vv,
         beta_names = nm, betas = as.numeric(m$betas),
         alpha = as.numeric(m$alpha), entropy = as.numeric(m$entropy),
         varmin = as.numeric(m$varmin[vv]), varmax = as.numeric(m$varmax[vv]),
         fmin = as.numeric(m$featuremins[nm]), fmax = as.numeric(m$featuremaxs[nm]),
         auc_tr = round(auc_tr, 4), auc_cv = round(cm[1], 4),
         tss_cv = round(cm[2], 4), thr_cv = round(cm[3], 6))
    # 실패도 지문과 함께 남긴다. 남기지 않으면 매 실행마다 같은 종을 다시 시도하고 또 실패한다.
    # 지문이 걸려 있으므로 그 종에 새 관측이 들어오면 자동으로 다시 시도된다.
  }, error = function(e) list(k = k, sig = it$sig, n = n, nvar = nv,
                              failed = conditionMessage(e)))
}

tot <- c(keep = 0L, refit = 0L, new = 0L, drop = 0L, fail = 0L)
TXS <- sort(unique(sc$tx))
if (!is.null(TAXA)) TXS <- intersect(TXS, TAXA)
for (TX in TXS) {                          # 루프 변수는 컬럼명(tx)과 겹치지 않게 둔다
  sub <- sc[tx == TX]
  items <- list(); sigs <- character(0)
  for (k in unique(sub$ktsn)) {
    cid <- sort(unique(sub[ktsn == k, cid]))
    r <- row_of[cid + 1L]; r <- r[r > 0]
    if (length(r) < MIN_N) next
    items[[k]] <- list(k = k, rows = r, sig = digest(cid))
  }
  if (!length(items)) next

  f <- file.path(STORE, sprintf("%s.json", txfile(TX)))
  old <- if (!FORCE && file.exists(f)) {
    j <- fromJSON(f, simplifyDataFrame = FALSE)
    if (identical(j$cfg, cfg)) setNames(j$sp, sapply(j$sp, function(x) x$k)) else list()
  } else list()

  same <- names(items)[sapply(names(items), function(k)
    !is.null(old[[k]]) && identical(old[[k]]$sig, items[[k]]$sig))]
  todo <- setdiff(names(items), same)
  isnew <- setdiff(todo, names(old))
  dropped <- setdiff(names(old), names(items))

  res <- list()
  if (length(todo)) {
    t0 <- Sys.time()
    cl <- makeCluster(NCORE)
    clusterExport(cl, c("ENV", "V", "WVAR", "WET", "N_BG", "KFOLD", "CLASSES", "TIERS",
                        "nvar_for", "roc_stats"), envir = environment())
    invisible(clusterEvalQ(cl, suppressMessages(library(maxnet))))
    res <- Filter(Negate(is.null), parLapply(cl, items[todo], fit_one))
    stopCluster(cl)
    el <- sprintf(" · %.1f분", as.numeric(difftime(Sys.time(), t0, units = "mins")))
  } else el <- ""

  sp <- c(unname(old[same]), unname(res))
  write_json(list(cfg = cfg, built = format(Sys.time(), "%Y-%m-%d %H:%M:%S"), sp = sp),
             f, auto_unbox = TRUE, digits = 8)
  nfail <- sum(sapply(sp, function(x) !is.null(x$failed)))
  tot <- tot + c(length(same), length(todo) - length(isnew), length(isnew),
                 length(dropped), nfail)
  cat(sprintf("[%-3s] 유지 %5d · 재적합 %5d · 신규 %4d · 제외 %4d → 모델 %5d (실패 %d)%s\n",
              TX, length(same), length(todo) - length(isnew), length(isnew),
              length(dropped), length(sp) - nfail, nfail, el))
  flush.console()
}
cat(sprintf("\n합계  유지 %s · 재적합 %s · 신규 %s · 제외 %s · 실패 %s  → %s\n",
            format(tot[1], big.mark = ","), format(tot[2], big.mark = ","),
            format(tot[3], big.mark = ","), format(tot[4], big.mark = ","),
            format(tot[5], big.mark = ","), STORE))
