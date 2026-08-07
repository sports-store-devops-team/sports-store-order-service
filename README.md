# Sports Store Order Service

FastAPI service that coordinates checkout and stores customer orders. It listens on port `8004`; health is available at `GET /health`.

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `MONGO_URI` | Yes | MongoDB connection URI for the order database. |
| `JWT_SECRET` | Yes | Shared JWT verification secret. |
| `CART_URL` | Yes | Base URL of the cart service. |
| `CATALOG_URL` | Yes | Base URL of the catalog service. |
| `PAYMENT_URL` | Yes | Base URL of the payment service. |
| `JWT_ALGORITHM` | No | JWT algorithm (default `HS256`). |
| `HTTP_TIMEOUT_SECONDS` | No | Downstream request timeout (default `5`). |
| `SHIPPING_FLAT_RATE` | No | Shipping charge below the threshold (default `5.00`). |
| `FREE_SHIPPING_THRESHOLD` | No | Free-shipping subtotal threshold (default `100`). |

`.env.example` contains development-only placeholders. Do not use them in production.

## Build and test

```sh
docker build -t sports-store/order-service:0.1.0 .
python -m pytest
```

Run locally with `uvicorn main:app --host 0.0.0.0 --port 8004`.

## Observability

`GET /metrics` exposes Prometheus process metrics plus request count and
latency metrics labeled only with service, method, normalized route template,
and status code. Application access events are one-line JSON on stdout;
Uvicorn's duplicate access log is disabled in the container command.

## Continuous integration

Pull requests targeting `main` run the pytest suite and a non-publishing container build. Pushes to `main` repeat validation, authenticate to AWS through GitHub OIDC, and publish exactly one immutable ECR image tagged `<VERSION>-<7-character-git-hash>`. `VERSION` is the semantic-version source and changes are made deliberately through a pull request.

Configure the Actions variables `AWS_REGION` and `AWS_ECR_PUBLISH_ROLE_ARN` at repository or organization scope. The role ARN is configuration, not a secret; no static AWS credentials are stored. CI does not deploy to EKS. Deployment is handled later through Argo CD.
