# Daftar Layanan AWS untuk Assessment

Tandai layanan yang ingin di-assessment dengan mengganti `[ ]` menjadi `[x]`

---

# Tabel Layanan AWS

## Compute Services

| No  | Services                         | Checklist |
| -----| ----------------------------------| -----------|
| 1   | EC2 (Elastic Compute Cloud)      | [x]       |
| 2   | Lambda                           | [ ]       |
| 3   | ECS (Elastic Container Service)  | [ ]       |
| 4   | EKS (Elastic Kubernetes Service) | [x]       |
| 5   | Fargate                          | [ ]       |
| 6   | ECR (Elastic Container Registry) | [x]       |

## Storage Services

| No  | Services                    | Checklist |
| -----| -----------------------------| -----------|
| 7   | S3 (Simple Storage Service) | [x]       |
| 8   | EBS (Elastic Block Store)   | [x]       |
| 9   | EFS (Elastic File System)   | [x]       |
| 10  | AWS Backup                  | [x]       |

## Database Services

| No  | Services                          | Checklist |
| -----| -----------------------------------| -----------|
| 11  | RDS (Relational Database Service) | [x]       |
| 12  | Aurora                            | [ ]       |
| 13  | DynamoDB                          | [ ]       |
| 14  | ElastiCache                       | [x]       |
| 15  | Redshift                          | [ ]       |

## Networking & Content Delivery

| No  | Services                        | Checklist |
| -----| ---------------------------------| -----------|
| 16  | VPC (Virtual Private Cloud)     | [x]       |
| 17  | CloudFront                      | [ ]       |
| 18  | Route 53                        | [x]       |
| 19  | Direct Connect                  | [ ]       |
| 20  | Application Load Balancer (ALB) | [x]       |
| 21  | Network Load Balancer (NLB)     | [x]       |
| 22  | NAT Gateway                     | [x]       |
| 23  | API Gateway                     | [ ]       |

## Security, Identity & Compliance

| No  | Services                             | Checklist |
| -----| --------------------------------------| -----------|
| 24  | IAM (Identity and Access Management) | [ ]       |
| 25  | KMS (Key Management Service)         | [x]       |
| 26  | Secrets Manager                      | [x]       |
| 27  | WAF (Web Application Firewall)       | [x]       |
| 28  | Shield                               | [ ]       |
| 29  | GuardDuty                            | [ ]       |
| 30  | Certificate Manager (ACM)            | [ ]       |
| 31  | Cognito                              | [ ]       |

## Management & Governance

| No  | Services        | Checklist |
| -----| -----------------| -----------|
| 32  | CloudWatch      | [x]       |
| 33  | CloudTrail      | [x]       |
| 34  | Config          | [x]       |
| 35  | Systems Manager | [ ]       |
| 36  | CloudFormation  | [ ]       |
| 37  | Organizations   | [ ]       |

## Application Integration

| No  | Services                                 | Checklist |
| -----| ------------------------------------------| -----------|
| 38  | SQS (Simple Queue Service)               | [ ]       |
| 39  | SNS (Simple Notification Service)        | [x]       |
| 40  | EventBridge                              | [ ]       |
| 41  | Step Functions                           | [ ]       |
| 42  | MSK (Managed Streaming for Apache Kafka) | [x]       |
| 43  | Amazon MQ                                | [x]       |

## Analytics

| No  | Services                | Checklist |
| -----| -------------------------| -----------|
| 44  | Athena                  | [ ]       |
| 45  | Kinesis                 | [ ]       |
| 46  | Glue                    | [x]       |
| 47  | EMR (Elastic MapReduce) | [ ]       |
| 48  | QuickSight              | [ ]       |

## Machine Learning

| No  | Services    | Checklist |
| -----| -------------| -----------|
| 49  | SageMaker   | [ ]       |
| 50  | Rekognition | [ ]       |
| 51  | Comprehend  | [ ]       |
| 52  | Lex         | [ ]       |
| 53  | Polly       | [ ]       |
| 54  | Bedrock     | [ ]       |

## Developer Tools

| No  | Services                             | Checklist |
| -----| --------------------------------------| -----------|
| 55  | CodeCommit                           | [ ]       |
| 56  | CodeBuild                            | [ ]       |
| 57  | CodeDeploy                           | [ ]       |
| 58  | CodePipeline                         | [ ]       |
| 59  | Cloud9                               | [ ]       |
| 60  | Amplify                              | [ ]       |

## Migration & Transfer

| No  | Services                             | Checklist |
| -----| --------------------------------------| -----------|
| 61  | Database Migration Service (DMS)     | [ ]       |
| 62  | DataSync                             | [ ]       |
| 63  | Snow Family                          | [ ]       |

## Cost Management

| No  | Services                             | Checklist |
| -----| --------------------------------------| -----------|
| 65  | Cost Explorer                        | [ ]       |
| 66  | Budgets                              | [ ]       |

---

## Contoh Penggunaan

Untuk menandai layanan yang ingin di-assessment, ubah `[ ]` menjadi `[x]`:

```markdown
| 1 | EC2 (Elastic Compute Cloud) | [x] |
| 2 | Lambda | [x] |
| 3 | ECS (Elastic Container Service) | [ ] |
```

---

**Catatan**: 
- Tandai dengan `[x]` untuk layanan yang ingin di-assessment
- Biarkan `[ ]` untuk layanan yang tidak perlu di-assessment
- Anda dapat menambahkan layanan baru di baris berikutnya jika diperlukan
