pipeline {
    agent any

    stages {

        stage('Build') {
            steps{
            sh 'sudo docker build -t phishingdetector:latest .'
       
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