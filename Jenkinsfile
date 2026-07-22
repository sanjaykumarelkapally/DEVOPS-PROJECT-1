pipeline {
    agent: any

    stages {
        stage('Checkout') {
            steps{
            sh 'mkdir Application'
            sh 'cd Application'
            sh 'git clone https://github.com/sanjaykumarelkapally/DEVOPS-PROJECT-1.git'
         }
        }

        stage('Build') {
            steps{
            sh 'docker build -t PhishingDetector:latest .'
       
        }
        }


        stage   ('Post_Build') {
           steps{
            echo 'Build completed successfully!'
        }
        }
    
        stage('Push') {
         steps{
            echo 'Pushing the Docker image to Docker Hub...'
        }
        }
}
}