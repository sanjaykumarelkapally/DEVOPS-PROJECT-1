Pipeline {
    agent: any
    environment {
        DOCKER_IMAGE = 'flaskapp:latest'
    }

    Stages {
        Stage('Checkout') {
            sh 'mkdir Application'
            sh 'cd Application'
            sh 'git clone https://github.com/sanjaykumarelkapally/DEVOPS-PROJECT-1.git'
        }

        Stage('Build') {
            sh 'docker build -t PhishingDetector:latest .'
        }

        Stage('Post_Build') {
            echo 'Build completed successfully!'
        }
    
        Stage('Push') {
            echo 'Pushing the Docker image to Docker Hub...'
        }
}
}