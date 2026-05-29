// Auto-dismiss flash messages after 4 seconds
document.addEventListener('DOMContentLoaded', function () {
  const flashes = document.querySelectorAll('.flash');
  flashes.forEach(function (el) {
    setTimeout(function () {
      el.style.transition = 'opacity .4s';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 400);
    }, 4000);
  });

  // Scroll to #comments anchor on page load if hash present
  if (window.location.hash === '#comments') {
    const target = document.getElementById('comments');
    if (target) {
      setTimeout(function () { target.scrollIntoView({ behavior: 'smooth' }); }, 100);
    }
  }
});
