FROM nginx:alpine
LABEL maintainer="edib"

# Copy static frontend into nginx html folder
COPY ./ /usr/share/nginx/html/

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
