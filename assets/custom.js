// Scroll-triggered fade-in using IntersectionObserver
(function(){
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
      }
    });
  }, { threshold: 0.12 });

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.fade-up').forEach(el => observer.observe(el));

    // Mouse parallax for hero-content
    const hero = document.querySelector('.hero-bg');
    const content = document.querySelector('.hero-content');
    if (hero && content) {
      hero.addEventListener('mousemove', (e) => {
        const rect = hero.getBoundingClientRect();
        const xx = (e.clientX - rect.left) / rect.width - 0.5;
        const yy = (e.clientY - rect.top) / rect.height - 0.5;
        content.style.transform = `translateX(${xx * 10}px) translateY(${yy * -8}px)`;
      });

      hero.addEventListener('mouseleave', () => {
        content.style.transform = '';
      });

      // Gentle floating when user is idle
      setTimeout(() => content.classList.add('float'), 1200);
    }

    // Smooth CTA: scroll to dashboard anchor on click
    document.querySelectorAll('.cta-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        // Post message for Streamlit host
        try{ window.parent.postMessage('go_dashboard', '*'); } catch(e){}
      });
    });
  });
})();
