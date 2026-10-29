"""PNG comparison using the existing browser canvas; no image dependencies."""
import base64


def difference(page, reference, current):
    images = ['data:image/png;base64,'+base64.b64encode(data).decode() for data in (reference,current)]
    return page.evaluate('''async images => {
      const load = src => new Promise((resolve,reject) => {
        const image = new Image(); image.onload = () => resolve(image); image.onerror = reject; image.src = src;
      });
      const [a,b] = await Promise.all(images.map(load));
      if(a.width !== b.width || a.height !== b.height) return {dimensionMismatch:true, ratio:1};
      const pixels = image => {const c=document.createElement('canvas');c.width=image.width;c.height=image.height;
        const ctx=c.getContext('2d');ctx.drawImage(image,0,0);return ctx.getImageData(0,0,c.width,c.height).data;};
      const x=pixels(a), y=pixels(b); let changed=0;
      for(let i=0;i<x.length;i+=4) {
        if(Math.max(Math.abs(x[i]-y[i]),Math.abs(x[i+1]-y[i+1]),Math.abs(x[i+2]-y[i+2])) > 24) changed++;
      }
      return {dimensionMismatch:false, ratio:changed/(a.width*a.height), changedPixels:changed};
    }''', images)
