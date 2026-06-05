const slides = document.querySelectorAll('.slide');
const dots = document.querySelectorAll('.slider-dot');
let index = 0;

function updateSlides() {
  slides.forEach((slide, i) => {
    slide.classList.remove('active', 'prev', 'next');
    if (i === index) slide.classList.add('active');
    else if (i === (index - 1 + slides.length) % slides.length) slide.classList.add('prev');
    else if (i === (index + 1) % slides.length) slide.classList.add('next');
  });
  dots.forEach((dot, i) => {
    dot.classList.remove('active');
    if (i === index) dot.classList.add('active');
  });
}

function showSlide() {
  index = (index + 1) % slides.length;
  updateSlides();
}

function prevSlide() {
  index = (index - 1 + slides.length) % slides.length;
  updateSlides();
}

function nextSlide() {
  index = (index + 1) % slides.length;
  updateSlides();
}

function goToSlide(i) {
  index = i;
  updateSlides();
}

if (slides.length > 0) {
  updateSlides();
  setInterval(showSlide, 5000);
}

const slider = document.querySelector('.slider');
if (slider) {
  let touchStartX = 0, touchEndX = 0;
  slider.addEventListener('touchstart', e => touchStartX = e.changedTouches[0].screenX, { passive: true });
  slider.addEventListener('touchend', e => {
    touchEndX = e.changedTouches[0].screenX;
    const diff = touchStartX - touchEndX;
    if (Math.abs(diff) > 50) diff > 0 ? nextSlide() : prevSlide();
  }, { passive: true });
}

function scrollProducts(direction, carouselId) {
  const carousel = document.getElementById(carouselId);
  if (carousel) carousel.scrollBy({ left: direction * 1800, behavior: 'smooth' });
}

function toggleMobileMenu() {
  const navList = document.querySelector('.nav-list');
  const mobileMenu = document.querySelector('.mobile-menu i');
  if (navList) navList.classList.toggle('active');
  if (mobileMenu) {
    mobileMenu.classList.toggle('fa-bars');
    mobileMenu.classList.toggle('fa-times');
  }
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

let currentImageIndex = 0;

function changeImage(index) {
  const adjustedIndex = index - 1;
  currentImageIndex = adjustedIndex;
  document.querySelectorAll('.carousel-img').forEach((img, i) => {
    img.classList.remove('active');
    if (i === adjustedIndex) img.classList.add('active');
  });
  document.querySelectorAll('.thumbnail').forEach((thumb, i) => {
    thumb.classList.remove('active');
    if (i === adjustedIndex) thumb.classList.add('active');
  });
  document.querySelectorAll('.carousel-dots .dot').forEach((dot, i) => {
    dot.classList.remove('active');
    if (i === adjustedIndex) dot.classList.add('active');
  });
}

const imageCarousel = document.querySelector('.image-carousel');
if (imageCarousel) {
  let touchStartX = 0, touchEndX = 0;
  imageCarousel.addEventListener('touchstart', e => touchStartX = e.changedTouches[0].screenX, { passive: true });
  imageCarousel.addEventListener('touchend', e => {
    touchEndX = e.changedTouches[0].screenX;
    const diff = touchStartX - touchEndX;
    const totalImages = document.querySelectorAll('.carousel-img').length;
    if (diff > 50) {
      currentImageIndex = (currentImageIndex + 1) % totalImages;
      changeImage(currentImageIndex + 1);
    } else if (diff < -50) {
      currentImageIndex = (currentImageIndex - 1 + totalImages) % totalImages;
      changeImage(currentImageIndex + 1);
    }
  }, { passive: true });
}

function openShareModal() {
  const modal = document.getElementById('shareModal');
  if (modal) modal.classList.add('active');
}

function closeShareModal() {
  const modal = document.getElementById('shareModal');
  if (modal) modal.classList.remove('active');
}

function closeQrModal() {
  const qrModal = document.querySelector('.qr-modal');
  if (qrModal) qrModal.remove();
}

function copyLinkFallback(text, shareToast) {
  // 创建临时 textarea 元素
  const textArea = document.createElement('textarea');
  textArea.value = text;
  textArea.style.position = 'fixed';
  textArea.style.left = '-9999px';
  textArea.style.top = '0';
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  
  try {
    const successful = document.execCommand('copy');
    if (successful && shareToast) {
      shareToast.classList.add('active');
      setTimeout(() => {
        shareToast.classList.remove('active');
        closeShareModal();
      }, 2000);
    } else if (successful) {
      closeShareModal();
    }
  } catch (err) {
    console.error('复制失败:', err);
    alert('复制失败，请手动复制链接: ' + text);
    closeShareModal();
  }
  
  document.body.removeChild(textArea);
}

function shareTo(platform) {
  const shareToast = document.getElementById('shareToast');
  const url = encodeURIComponent(window.location.href);
  const originalUrl = window.location.href;
  let shouldCloseModal = true;
  
  switch (platform) {
    case 'copy':
      shouldCloseModal = false;
      // 尝试使用现代 Clipboard API
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(originalUrl).then(() => {
          if (shareToast) {
            shareToast.classList.add('active');
            setTimeout(() => {
              shareToast.classList.remove('active');
              closeShareModal();
            }, 2000);
          } else {
            closeShareModal();
          }
        }).catch(err => {
          // 如果失败，使用备用方法
          copyLinkFallback(originalUrl, shareToast);
        });
      } else {
        // 使用备用方法
        copyLinkFallback(originalUrl, shareToast);
      }
      break;
    case 'email':
      window.location.href = `mailto:?subject=查看这个产品&body=${url}`;
      break;
    case 'whatsapp':
      window.open(`https://wa.me/?text=${url}`, '_blank');
      break;
    case 'facebook':
      window.open(`https://www.facebook.com/sharer/sharer.php?u=${url}`, '_blank');
      break;
    case 'pinterest':
      window.open(`https://pinterest.com/pin/create/button/?url=${url}`, '_blank');
      break;
    case 'x':
    case 'twitter':
      window.open(`https://twitter.com/intent/tweet?url=${url}`, '_blank');
      break;
    case 'qr':
      const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${url}`;
      const qrModal = document.createElement('div');
      qrModal.className = 'qr-modal';
      qrModal.innerHTML = `
        <div class="qr-modal-overlay" onclick="closeQrModal()"></div>
        <div class="qr-modal-content">
          <button class="qr-close" onclick="closeQrModal()"><i class="fas fa-times"></i></button>
          <h3>Scan QR Code</h3>
          <img src="${qrUrl}" alt="QR Code" class="qr-code">
          <p>Scan with your phone to open this product</p>
        </div>
      `;
      document.body.appendChild(qrModal);
      break;
    case 'messages':
      window.open(`sms:&body=${url}`, '_blank');
      break;
    case 'messenger':
      window.open(`fb-messenger://share?link=${url}`, '_blank');
      break;
  }
  if (shouldCloseModal) {
    closeShareModal();
  }
}

function scrollRelatedProducts(direction) {
  const relatedGrid = document.getElementById('relatedGrid');
  if (relatedGrid) relatedGrid.scrollBy({ left: direction * 900, behavior: 'smooth' });
}

function initStickyHeader() {
  const discountBanner = document.querySelector('.discount-banner');
  const headerLogoRow = document.querySelector('.header-logo-row');
  
  if (!discountBanner || !headerLogoRow) return;
  
  const bannerHeight = discountBanner.offsetHeight;
  const logoRowHeight = headerLogoRow.offsetHeight;
  
  window.addEventListener('scroll', () => {
    const scrollY = window.scrollY;
    
    if (scrollY > bannerHeight) {
      discountBanner.classList.add('sticky-fixed');
    } else {
      discountBanner.classList.remove('sticky-fixed');
    }
    
    if (scrollY >= bannerHeight) {
      headerLogoRow.classList.add('sticky-fixed');
    } else {
      headerLogoRow.classList.remove('sticky-fixed');
    }
    
    const navRow = document.querySelector('.header-nav-row');
    if (navRow) {
      if (scrollY >= bannerHeight + logoRowHeight) {
        navRow.style.top = `${bannerHeight + logoRowHeight}px`;
      } else {
        navRow.style.top = '';
      }
    }
  });
}

document.addEventListener('DOMContentLoaded', initStickyHeader);