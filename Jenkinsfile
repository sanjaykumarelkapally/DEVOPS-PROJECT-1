pipeline {
    agent any

    environment {
        AWS_REGION     = "ap-south-1"
        AWS_ACCOUNT_ID = "028282962676"
        ECR_REPO       = "sanjaykumar/phishing_detector"
        IMAGE_URI      = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:latest"
        DEPLOY_HOST    = "13.232.162.156"
    }

    stages {

        stage('Build Image') {
            steps {
                sh 'docker build -t phishing_detector:latest .'
            }
        }

        stage('Login to ECR') {
            steps {
                sh '''
                    aws ecr get-login-password --region $AWS_REGION | \
                    docker login \
                        --username AWS \
                        --password-stdin \
                        $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
                '''
            }
        }

        stage('Tag Image') {
            steps {
                sh '''
                    docker tag phishing_detector:latest $IMAGE_URI
                '''
            }
        }

        stage('Push Image') {
            steps {
                sh '''
                    docker push $IMAGE_URI
                '''
            }
        }

        stage('Deploy') {
            steps {
                sshagent(credentials: ['deployment-ec2-key']) {
                    sh """
                        ssh -o StrictHostKeyChecking=no ubuntu@${DEPLOY_HOST} '
                            set -e

                            aws ecr get-login-password --region ${AWS_REGION} | docker login \
                                --username AWS \
                                --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com

                            docker pull ${IMAGE_URI}

                            docker stop phishing-detector || true
                            docker rm phishing-detector || true

                            docker run -d \
                                --name phishing-detector \
                                --restart unless-stopped \
                                -p 5001:5001 \
                                ${IMAGE_URI}

                            docker image prune -f

                            docker ps
                        '
                    """
                }
            }
        }

        stage('Post Build') {
            steps {
                echo '=========================================='
                echo 'Deployment completed successfully!'
                echo 'Docker image built.'
                echo 'Image pushed to Amazon ECR.'
                echo 'Application deployed to EC2.'
                echo '=========================================='
            }
        }
    }

    post {
        success {
            echo 'CI/CD Pipeline executed successfully.'
        }

        failure {
            echo 'CI/CD Pipeline failed.'
        }

        always {
            cleanWs()
        }
    }
}