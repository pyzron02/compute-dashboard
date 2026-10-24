# API keys for the remaining collectors

All four are free. Each key goes into the repo as a GitHub Actions secret, never into code:
open https://github.com/pyzron02/compute-dashboard/settings/secrets/actions, click
**New repository secret**, and paste the name and value shown below.

Do them in any order; each collector switches on as soon as its secret exists.

## 1. AWS (on-demand and spot prices) — about 10 minutes

The pricing and spot-history APIs cost nothing, but they need an AWS account.

1. Sign in at https://console.aws.amazon.com (create a free account if needed).
2. Open **IAM → Users → Create user**. Name it `compute-dashboard`. Do not give it console access.
3. On the permissions step choose **Attach policies directly → Create policy → JSON** and paste:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["pricing:GetProducts", "ec2:DescribeSpotPriceHistory"],
       "Resource": "*"
     }]
   }
   ```
   Name the policy `compute-dashboard-read-prices`, then attach it to the user. This key can read prices and nothing else.
4. Open the user → **Security credentials → Create access key → Application running outside AWS**.
5. Add two secrets: `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

## 2. Google Cloud (GPU and spot SKU prices) — about 5 minutes

1. Go to https://console.cloud.google.com and create a project named `compute-dashboard`.
2. Open **APIs & Services → Library**, search **Cloud Billing API**, click **Enable**.
3. Open **APIs & Services → Credentials → Create credentials → API key**.
4. Click **Edit API key → API restrictions → Restrict key** and tick only **Cloud Billing API**.
5. Add secret `GCP_API_KEY`.

Reading the public price catalog is free. If Google asks for a billing account, you can skip it for this API.

## 3. Vast.ai (marketplace GPU prices) — about 2 minutes

1. Sign up at https://cloud.vast.ai (no credit needed to read offers).
2. Open **Account → Keys** and copy the API key.
3. Add secret `VAST_API_KEY`.

## 4. OpenRouter (daily tokens by model) — about 2 minutes

1. Sign up at https://openrouter.ai.
2. Open **Settings → Keys → Create key**. Set the credit limit to `0`, since the dashboard only reads usage data.
3. Add secret `OPENROUTER_API_KEY`.

## Check

When you're done, reply in the thread. I'll run the workflow and confirm each source collected data.
