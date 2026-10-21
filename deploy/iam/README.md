# IAM policy'leri

Yer tutucular (`__REGION__`, `__ACCOUNT_ID__` …) `deploy/aws/render.py` ile doldurulur. Komutlar: [docs/DEPLOY_AWS.md](../../docs/DEPLOY_AWS.md).

| Dosya | Ne için |
|---|---|
| `ec2-trust-policy.json` | `newsradar-ec2-role`'ü yalnızca EC2 üstlenebilir. |
| `ec2-instance-policy.json` | Rolün inline policy'si (`newsradar-ec2-inline`). AWS-managed `AmazonSSMManagedInstanceCore` ayrıca eklenir (Session Manager). |
| `frontend-bucket-policy.json` | Frontend bucket'ını yalnızca bu CloudFront dağıtımı (OAC) okuyabilir. |
| `github-oidc-trust-policy.json` | GitHub Actions rollerini yalnızca bu reponun `main` dalındaki iş akışları üstlenebilir (OIDC; anahtar yok). |
| `github-backend-policy.json` | `newsradar-github-backend`: tek ECR reposuna push + etiket, yalnızca API instance'ına `AWS-RunShellScript`, komut sonucunu okuma. |
| `github-frontend-policy.json` | `newsradar-github-frontend`: yalnızca frontend bucket'ına yazma/silme + o dağıtımda invalidation. |

`ec2-instance-policy.json`'da `"Resource": "*"` içeren tek ifade `ecr:GetAuthorizationToken`. Bu eylem kaynak bazlı kısıtlamayı desteklemiyor; AWS yalnızca `*` kabul ediyor. Token tek başına hiçbir image'a erişim vermez: çekme izni yalnızca `newsradar-api` reposuyla sınırlı (`PullBackendImage`).

`github-backend-policy.json`'da da iki `*` var: `ecr:GetAuthorizationToken` ve `ssm:GetCommandInvocation` (komut sonucunu okuma). İkisi de AWS'nin Service Authorization Reference'ına göre kaynak bazlı kısıtlamayı desteklemiyor. Komut gönderme (`ssm:SendCommand`) ise yalnızca tek instance ve `AWS-RunShellScript` dokümanıyla sınırlı.
