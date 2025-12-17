const canvas = document.getElementById('gameCanvas');
const ctx = canvas.getContext('2d');
const scoreElement = document.getElementById('score');
const highScoreElement = document.getElementById('highScore');
const finalScoreElement = document.getElementById('finalScore');
const gameOverScreen = document.getElementById('gameOver');
const restartBtn = document.getElementById('restartBtn');
const leftBtn = document.getElementById('leftBtn');
const rightBtn = document.getElementById('rightBtn');

canvas.width = 460;
canvas.height = 600;

let gameRunning = true;
let score = 0;
let highScore = localStorage.getItem('skyJumpHighScore') || 0;
highScoreElement.textContent = highScore;

const player = {
    x: canvas.width / 2 - 25,
    y: canvas.height - 150,
    width: 50,
    height: 50,
    velocityY: 0,
    velocityX: 0,
    jumping: false,
    color: '#FF6B6B'
};

const gravity = 0.5;
const jumpStrength = -15;
const moveSpeed = 7;
const maxVelocityX = 8;

let platforms = [];
const platformWidth = 80;
const platformHeight = 15;
const platformGap = 80;

let keys = {
    left: false,
    right: false
};

function initPlatforms() {
    platforms = [];

    platforms.push({
        x: canvas.width / 2 - platformWidth / 2,
        y: canvas.height - 50,
        width: platformWidth,
        height: platformHeight,
        color: '#4ECDC4'
    });

    for (let i = 1; i < 10; i++) {
        platforms.push({
            x: Math.random() * (canvas.width - platformWidth),
            y: canvas.height - 50 - (i * platformGap),
            width: platformWidth,
            height: platformHeight,
            color: '#4ECDC4'
        });
    }
}

function drawPlayer() {
    ctx.fillStyle = player.color;
    ctx.beginPath();
    ctx.arc(player.x + player.width / 2, player.y + player.height / 2, player.width / 2, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = 'white';
    ctx.beginPath();
    ctx.arc(player.x + 15, player.y + 18, 5, 0, Math.PI * 2);
    ctx.arc(player.x + 35, player.y + 18, 5, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#333';
    ctx.beginPath();
    ctx.arc(player.x + 15, player.y + 18, 2, 0, Math.PI * 2);
    ctx.arc(player.x + 35, player.y + 18, 2, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = '#333';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(player.x + 25, player.y + 35, 8, 0, Math.PI);
    ctx.stroke();
}

function drawPlatforms() {
    platforms.forEach(platform => {
        ctx.fillStyle = platform.color;
        ctx.fillRect(platform.x, platform.y, platform.width, platform.height);

        ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.fillRect(platform.x, platform.y, platform.width, platform.height / 2);
    });
}

function updatePlayer() {
    if (keys.left) {
        player.velocityX = -moveSpeed;
    } else if (keys.right) {
        player.velocityX = moveSpeed;
    } else {
        player.velocityX *= 0.8;
    }

    player.velocityX = Math.max(-maxVelocityX, Math.min(maxVelocityX, player.velocityX));
    player.x += player.velocityX;

    if (player.x < -player.width) {
        player.x = canvas.width;
    } else if (player.x > canvas.width) {
        player.x = -player.width;
    }

    player.velocityY += gravity;
    player.y += player.velocityY;

    if (player.velocityY > 0) {
        platforms.forEach(platform => {
            if (player.x + player.width > platform.x &&
                player.x < platform.x + platform.width &&
                player.y + player.height > platform.y &&
                player.y + player.height < platform.y + platform.height + 15 &&
                player.velocityY > 0) {

                player.velocityY = jumpStrength;
                player.jumping = true;

                const jumpScore = Math.floor(Math.abs(platform.y - canvas.height) / 10);
                if (jumpScore > score) {
                    score = jumpScore;
                    scoreElement.textContent = score;
                }
            }
        });
    }

    if (player.y < canvas.height / 3 && player.velocityY < 0) {
        const scrollSpeed = -player.velocityY;

        platforms.forEach(platform => {
            platform.y += scrollSpeed;
        });

        platforms = platforms.filter(platform => platform.y < canvas.height + 50);

        while (platforms.length < 10) {
            const lastPlatform = platforms[platforms.length - 1];
            platforms.push({
                x: Math.random() * (canvas.width - platformWidth),
                y: lastPlatform.y - platformGap,
                width: platformWidth,
                height: platformHeight,
                color: '#4ECDC4'
            });
        }

        score += Math.floor(scrollSpeed);
        scoreElement.textContent = score;
    }

    if (player.y > canvas.height) {
        gameOver();
    }
}

function gameOver() {
    gameRunning = false;

    if (score > highScore) {
        highScore = score;
        localStorage.setItem('skyJumpHighScore', highScore);
        highScoreElement.textContent = highScore;
    }

    finalScoreElement.textContent = score;
    gameOverScreen.classList.remove('hidden');
}

function drawBackground() {
    const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
    gradient.addColorStop(0, '#87CEEB');
    gradient.addColorStop(1, '#E0F6FF');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
    for (let i = 0; i < 20; i++) {
        const x = (Date.now() / 100 + i * 50) % canvas.width;
        const y = (i * 73) % canvas.height;
        ctx.beginPath();
        ctx.arc(x, y, 2, 0, Math.PI * 2);
        ctx.fill();
    }
}

function gameLoop() {
    if (!gameRunning) return;

    drawBackground();
    drawPlatforms();
    updatePlayer();
    drawPlayer();

    requestAnimationFrame(gameLoop);
}

function resetGame() {
    gameRunning = true;
    score = 0;
    scoreElement.textContent = score;

    player.x = canvas.width / 2 - 25;
    player.y = canvas.height - 150;
    player.velocityY = 0;
    player.velocityX = 0;

    initPlatforms();
    gameOverScreen.classList.add('hidden');
    gameLoop();
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') {
        keys.left = true;
        e.preventDefault();
    }
    if (e.key === 'ArrowRight') {
        keys.right = true;
        e.preventDefault();
    }
});

document.addEventListener('keyup', (e) => {
    if (e.key === 'ArrowLeft') {
        keys.left = false;
    }
    if (e.key === 'ArrowRight') {
        keys.right = false;
    }
});

leftBtn.addEventListener('mousedown', () => keys.left = true);
leftBtn.addEventListener('mouseup', () => keys.left = false);
leftBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    keys.left = true;
});
leftBtn.addEventListener('touchend', (e) => {
    e.preventDefault();
    keys.left = false;
});

rightBtn.addEventListener('mousedown', () => keys.right = true);
rightBtn.addEventListener('mouseup', () => keys.right = false);
rightBtn.addEventListener('touchstart', (e) => {
    e.preventDefault();
    keys.right = true;
});
rightBtn.addEventListener('touchend', (e) => {
    e.preventDefault();
    keys.right = false;
});

restartBtn.addEventListener('click', resetGame);

initPlatforms();
gameLoop();
