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
| 20  | Elastic Load Balancing (ELB)    | [x]       |
| 21  | Application Load Balancer (ALB) | [x]       |
| 22  | Network Load Balancer (NLB)     | [x]       |
| 23  | NAT Gateway                     | [x]       |
| 24  | API Gateway                     | [ ]       |

## Security, Identity & Compliance

| No  | Services                             | Checklist |
| -----| --------------------------------------| -----------|
| 25  | IAM (Identity and Access Management) | [ ]       |
| 26  | KMS (Key Management Service)         | [x]       |
| 27  | Secrets Manager                      | [x]       |
| 28  | WAF (Web Application Firewall)       | [x]       |
| 29  | Shield                               | [ ]       |
| 30  | GuardDuty                            | [ ]       |
| 31  | Certificate Manager (ACM)            | [ ]       |
| 32  | Cognito                              | [ ]       |

## Management & Governance

| No  | Services        | Checklist |
| -----| -----------------| -----------|
| 33  | CloudWatch      | [x]       |
| 34  | CloudTrail      | [x]       |
| 35  | Config          | [x]       |
| 36  | Systems Manager | [ ]       |
| 37  | CloudFormation  | [ ]       |
| 38  | Organizations   | [ ]       |

## Application Integration

| No  | Services                                 | Checklist |
| -----| ------------------------------------------| -----------|
| 39  | SQS (Simple Queue Service)               | [ ]       |
| 40  | SNS (Simple Notification Service)        | [x]       |
| 41  | EventBridge                              | [ ]       |
| 42  | Step Functions                           | [ ]       |
| 43  | MSK (Managed Streaming for Apache Kafka) | [x]       |
| 44  | Amazon MQ                                | [x]       |

## Analytics

| No  | Services                | Checklist |
| -----| -------------------------| -----------|
| 45  | Athena                  | [ ]       |
| 46  | Kinesis                 | [ ]       |
| 47  | Glue                    | [x]       |
| 48  | EMR (Elastic MapReduce) | [ ]       |
| 49  | QuickSight              | [ ]       |

## Machine Learning

| No  | Services    | Checklist |
| -----| -------------| -----------|
| 50  | SageMaker   | [ ]       |
| 51  | Rekognition | [ ]       |
| 52  | Comprehend  | [ ]       |
| 53  | Lex         | [ ]       |
| 54  | Polly       | [ ]       |
| 55  | Bedrock     | [ ]       |

## Developer Tools

| No  | Services                             | Checklist |
| -----| --------------------------------------| -----------|
| 56  | CodeCommit                           | [ ]       |
| 57  | CodeBuild                            | [ ]       |
| 58  | CodeDeploy                           | [ ]       |
| 59  | CodePipeline                         | [ ]       |
| 60  | Cloud9                               | [ ]       |
| 61  | Amplify                              | [ ]       |

## Migration & Transfer

| No  | Services                             | Checklist |
| -----| --------------------------------------| -----------|
| 62  | Database Migration Service (DMS)     | [ ]       |
| 63  | DataSync                             | [ ]       |
| 64  | Snow Family                          | [ ]       |

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
