FROM nginx:alpine
COPY index.html style.css script.js hero-salgados.jpg /usr/share/nginx/html/
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
