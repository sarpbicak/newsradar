# IAM policy'leri

Yer tutucular (`__REGION__`, `__ACCOUNT_ID__` …) `deploy/aws/render.py` ile doldurulur. Komutlar: [docs/DEPLOY_AWS.md](../../docs/DEPLOY_AWS.md).

| Dosya | Ne için |
|---|---|
| `ec2-trust-policy.json` | `newsradar-ec2-role`'ü yalnızca EC2 üstlenebilir. |
| `ec2-instance-policy.json` | Rolün inline policy'si (`newsradar-ec2-inline`). AWS-managed `AmazonSSMManagedInstanceCore` ayrıca eklenir (Session Manager). |
| `frontend-bucket-policy.json` | Frontend bucket'ını yalnızca bu CloudFront dağıtımı (OAC) okuyabilir. |

`ec2-instance-policy.json`'da `"Resource": "*"` içeren tek ifade `ecr:GetAuthorizationToken`. Bu eylem kaynak bazlı kısıtlamayı desteklemiyor; AWS yalnızca `*` kabul ediyor. Token tek başına hiçbir image'a erişim vermez: çekme izni yalnızca `newsradar-api` reposuyla sınırlı (`PullBackendImage`).
