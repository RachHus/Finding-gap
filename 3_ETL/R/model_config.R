# -*- coding: utf-8 -*-
# model_config.R — 관찰 추천도 모델의 설정 한 벌. env_grid_model.R · model_species.R ·
# seed_model_store.R 이 함께 source 한다.
#
# 한곳에 모은 이유: 이 값들은 cfg 해시로 묶여 "전 종 재적합" 판단에 쓰인다. 두 스크립트가 각자
# 상수를 들고 있으면 한쪽만 고쳤을 때 해시가 갈라져 8,900종이 이유 없이 다시 돌아간다.
#
# SCALE 이 중요하다. 브라우저는 env_grid.js 의 정수 스케일 값을 되돌려 쓰므로, 모델도 같은
# 정밀도의 값으로 학습해야 학습값과 예측값이 어긋나지 않는다. 그래서 격자를 만들 때부터
# 배포 정밀도로 반올림한다.
V       <- c("dem", "ndvi", "bio01", "bio18", "bio03", "bio14")   # A안(중첩 순서, VIF 최대 4.63)
SCALE   <- c(dem = 1, ndvi = 1000, bio01 = 10, bio18 = 1, bio03 = 10, bio14 = 1)
CLASSES <- "lq"       # linear + quadratic — 계수가 닫힌 형태로 남아 브라우저에서 계산 가능
N_BG    <- 10000L     # 배경 표본(경관 표본; 존재 셀을 배제하지 않는다 = MaxEnt 정의)
KFOLD   <- 4L
MIN_N   <- 10L        # 이보다 적으면 모델을 세우지 않는다(계절 축만 제공)
TIERS   <- c(30L, 60L, 100L)   # 점유 셀 수 경계 → 변수 3/4/5/6개
TSS_GATE <- 0.4       # 공간 점수를 내보낼 최소 교차검증 TSS(통상 기준: 0.4 fair · 0.6 good)

nvar_for <- function(n) 3L + sum(n >= TIERS)

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
  digest::digest(list(V = V, scale = SCALE, classes = CLASSES, n_bg = N_BG,
                      kfold = KFOLD, min_n = MIN_N, tiers = TIERS,
                      env = digest::digest(as.matrix(env_mat)),
                      cid = digest::digest(cid)))
}
