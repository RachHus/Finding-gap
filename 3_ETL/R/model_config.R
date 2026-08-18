# -*- coding: utf-8 -*-
# model_config.R — 관찰 추천도 모델의 공용 설정 한 벌.
#
# 이 파일을 source하는 스크립트(3_ETL/R/):
#   - env_grid_model.R (run_pipeline.py 단계 9) → env_grid_model.csv (모형 변수 포함 격자)
#   - model_species.R (run_pipeline.py 단계 11) → model_store/ (종별 maxnet 적합)
#   - seed_model_store.R (run_pipeline.py 스코프 외, 초기화용) → model_store/
#
# 이 파일의 값을 바꾸면 cfg 해시가 갈라져 다음을 다시 실행해야 함:
#   - run_pipeline.py 단계 9(env_grid_model) 이후 재실행 → 11(model) 전량 재적합 필요
#   - 특히 V·WVAR·SCALE·CLASSES·N_BG·KFOLD 중 하나라도 바뀌면 전 종(약 8,900종) 재적합
#     (각 종 5회 CV = 약 10시간 소요)
#
# 한곳에 모은 이유: 여러 스크립트가 각자 상수를 들고 있으면 한쪽만 고쳤을 때 해시가 갈라진다.
# SCALE은 특히 중요하다. 브라우저는 env_grid.js의 정수 스케일 값을 읽으므로,
# 모델도 같은 정밀도로 학습해야 학습값·예측값이 어긋나지 않는다(격자 생성 단계부터
# 배포 정밀도로 반올림함).
V       <- c("dem", "ndvi", "bio01", "bio18", "bio03", "bio14")   # A안(중첩 순서, VIF 최대 4.63)
WVAR    <- "sord"     # 수생종에만 추가로 배정하는 변수(하천 차수) — 아래 설명
SCALE   <- c(dem = 1, ndvi = 1000, bio01 = 10, bio18 = 1, bio03 = 10, bio14 = 1, sord = 1)
CLASSES <- "lq"       # linear + quadratic — 계수가 닫힌 형태로 남아 브라우저에서 계산 가능
N_BG    <- 10000L     # 배경 표본(경관 표본; 존재 셀을 배제하지 않는다 = MaxEnt 정의)
KFOLD   <- 4L
MIN_N   <- 10L        # 이보다 적으면 모델을 세우지 않는다(계절 축만 제공)
TIERS   <- c(30L, 60L, 100L)   # 점유 셀 수 경계 → 변수 3/4/5/6개

nvar_for <- function(n) 3L + sum(n >= TIERS)

# WVAR 을 V 에 넣지 않고 따로 둔 이유. V 는 점유 셀 수에 따라 앞에서부터 잘라 쓰는 목록이라
# (nvar_for), 뒤에 덧붙이면 상위 구간 종만 받고 하위 구간 종은 영영 못 받는다. 또 이 변수는
# 물속에 사는 종에게만 뜻이 있다 — 육상종에게 하천 차수를 주면 조사가 몰린 하천 주변을
# 외우는 데나 쓰인다. 그래서 "수생종이면 한 개 더"라는 별도 규칙으로 배정한다.
#
# 검증: 수생종 684종을 실제로 다시 적합해 비교했을 때, 후보 칸이 놓이는 하천의 크기가
# 관측 하천 크기에 가까워졌다(차이 0.423 → 0.237, 63% 종이 개선, p ≈ 2e-35). 이 변수를
# 뽑지 않은 17종은 지도가 거의 그대로였다(자카드 0.973) — 효과가 변수에서 온 것이 맞다.

# ROC 한 번으로 AUC · max-TSS · 그때의 임계값을 함께 낸다. max-TSS = max(민감도+특이도-1) = Youden J.
roc_stats <- function(score, y) {
  o <- order(-score); yy <- y[o]
  n1 <- sum(y == 1); n0 <- sum(y == 0)
  if (n1 == 0 || n0 == 0) return(c(NA_real_, NA_real_, NA_real_))
  tpr <- cumsum(yy == 1) / n1
  fpr <- cumsum(yy == 0) / n0
  j <- tpr - fpr; i <- which.max(j)
  auc <- sum(diff(c(0, fpr)) * (tpr + c(0, tpr[-length(tpr)])) / 2)
  c(auc, j[i], sort(score, decreasing = TRUE)[i])
}

# 격자 내용까지 해시에 넣는다 — 환경 레이어가 다시 만들어지면 모든 모델의 전제가 달라지므로
# 부분 갱신으로 살릴 수 없다(서로 다른 전제의 모델이 한 자산에 섞이면 안 된다).
model_cfg <- function(env_mat, cid) {
  digest::digest(list(V = V, wvar = WVAR, scale = SCALE, classes = CLASSES, n_bg = N_BG,
                      kfold = KFOLD, min_n = MIN_N, tiers = TIERS,
                      env = digest::digest(as.matrix(env_mat)),
                      cid = digest::digest(cid)))
}
