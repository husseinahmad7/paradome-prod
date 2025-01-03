var x = document.getElementById("personal-img");

if (x) {
  x.addEventListener("mouseover", showMyPic, false);

}

function showMyPic()
{
   document.getElementById("myname").setAttribute("style", "display:flex;align-content: center;align-items: center;justify-content: center;transform: translate(5vw,40vh)")
}

let scrolling = false;
let m = document.querySelector('.shooting-star');


let sec2 = document.querySelector('#section-upcom');


window.onscroll = () => {
    scrolling = true;
};

setInterval(() => {
    if (scrolling) {
        scrolling = false;
        // let num = 6000;

        // num = Math.round(Math.random()*5000)+3000;
        m.style.setProperty('top',Math.round(Math.random()*89) + 10 +'%');
        // m.style.setProperty('--time', num +'ms');
    }
},18000);



  //stars particles 
particlesJS("particles-js", {"particles":{"number":{"value":80,"density":{"enable":true,"value_area":800}},"color":{"value":"#ffffff"},"shape":{"type":"star","stroke":{"width":0,"color":"#000000"},"polygon":{"nb_sides":5},"image":{"src":"img/github.svg","width":100,"height":100}},"opacity":{"value":0.5,"random":false,"anim":{"enable":false,"speed":1,"opacity_min":0.1,"sync":false}},"size":{"value":3,"random":true,"anim":{"enable":false,"speed":40,"size_min":0.1,"sync":false}},"line_linked":{"enable":true,"distance":150,"color":"#ffffff","opacity":0.4,"width":1},"move":{"enable":true,"speed":6,"direction":"none","random":false,"straight":false,"out_mode":"out","bounce":false,"attract":{"enable":false,"rotateX":600,"rotateY":1200}}},"interactivity":{"detect_on":"canvas","events":{"onhover":{"enable":true,"mode":"grab"},"onclick":{"enable":true,"mode":"repulse"},"resize":true},"modes":{"grab":{"distance":400,"line_linked":{"opacity":1}},"bubble":{"distance":400,"size":40,"duration":2,"opacity":8,"speed":3},"repulse":{"distance":200,"duration":0.4},"push":{"particles_nb":4},"remove":{"particles_nb":2}}},"retina_detect":true});
// var count_particles, stats, update; stats = new Stats; stats.setMode(0); 
// stats.domElement.style.position = 'absolute'; stats.domElement.style.left = '0px'; 
// stats.domElement.style.top = '0px'; document.body.appendChild(stats.domElement); 
count_particles = document.querySelector('.js-count-particles');
 update = function() { 
    // // stats.begin(); stats.end(); 
    // if (window.pJSDom[0].pJS.particles && window.pJSDom[0].pJS.particles.array) 
    // { count_particles.innerText = window.pJSDom[0].pJS.particles.array.length; } 
    requestAnimationFrame(update); }; 
requestAnimationFrame(update);;

// Smooth scroll for navigation links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// Enhanced personal image interaction
var personalImg = document.getElementById("personal-img");
if (personalImg) {
    personalImg.addEventListener("mouseover", function() {
        document.getElementById("myname").style.transform = "translate(5vw,40vh) scale(1.1)";
        document.getElementById("myname").style.transition = "all 0.3s ease";
    });
    
    personalImg.addEventListener("mouseout", function() {
        document.getElementById("myname").style.transform = "translate(5vw,40vh) scale(1)";
    });
}

// Intersection Observer for fade-in animations
const observerOptions = {
    threshold: 0.1
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('fade-in');
            entry.target.style.opacity = 1;
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Apply fade-in animation to sections
document.querySelectorAll('section').forEach(section => {
    section.style.opacity = 0;
    section.style.transform = 'translateY(20px)';
    section.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(section);
});

// Enhanced shooting star animation
let shootingStar = document.querySelector('.shooting-star');
// let scrolling = false;

window.onscroll = () => {
    scrolling = true;
};

setInterval(() => {
    if (scrolling) {
        scrolling = false;
        if (shootingStar) {
            shootingStar.style.setProperty('top', Math.round(Math.random() * 89) + 10 + '%');
            shootingStar.style.setProperty('left', '-10%');
            shootingStar.style.animation = 'none';
            shootingStar.offsetHeight; // Trigger reflow
            shootingStar.style.animation = 'shoot 3s ease-out forwards';
        }
    }
}, 3000);

// Particles.js configuration with optimized settings
particlesJS("particles-js", {"particles":{"number":{"value":80,"density":{"enable":true,"value_area":800}},"color":{"value":"#ffffff"},"shape":{"type":"star","stroke":{"width":0,"color":"#000000"},"polygon":{"nb_sides":5},"image":{"src":"img/github.svg","width":100,"height":100}},"opacity":{"value":0.5,"random":false,"anim":{"enable":false,"speed":1,"opacity_min":0.1,"sync":false}},"size":{"value":3,"random":true,"anim":{"enable":false,"speed":40,"size_min":0.1,"sync":false}},"line_linked":{"enable":true,"distance":150,"color":"#ffffff","opacity":0.4,"width":1},"move":{"enable":true,"speed":6,"direction":"none","random":false,"straight":false,"out_mode":"out","bounce":false,"attract":{"enable":false,"rotateX":600,"rotateY":1200}}},"interactivity":{"detect_on":"canvas","events":{"onhover":{"enable":true,"mode":"grab"},"onclick":{"enable":true,"mode":"repulse"},"resize":true},"modes":{"grab":{"distance":400,"line_linked":{"opacity":1}},"bubble":{"distance":400,"size":40,"duration":2,"opacity":8,"speed":3},"repulse":{"distance":200,"duration":0.4},"push":{"particles_nb":4},"remove":{"particles_nb":2}}},"retina_detect":true});

// custom cursor

// const cursor = document.querySelector('.cursor');
// const introSec = document.querySelector('#section-intro');
// introSec.onhover= e => {
//   cursor.setAttribute("style", "top: "+(e.pageY - 10)+"px; left: "+(e.pageX - 10)+"px;");
//   console.log('tst')};
// introSec.addEventListener('mousemove', e => {
//     cursor.setAttribute("style", "top: "+(e.pageY - 10)+"px; left: "+(e.pageX - 10)+"px;");
//     console.log('tst')
// })

// introSec.addEventListener('click', () => {
//     cursor.classList.add("expand");
//     console.log('teest');

//     setTimeout(() => {
//         cursor.classList.remove("expand");
//     }, 500)
// })