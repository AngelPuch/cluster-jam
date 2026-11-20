package com.clusterjam.catalog.infrastructure.images;

import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.util.Arrays;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Pixels;
import com.clusterjam.catalog.application.photos.PhotoFailure;
import com.clusterjam.catalog.application.photos.PhotoFailure.Reason;
import com.clusterjam.catalog.application.ports.PhotoImages;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.MemoryCacheImageInputStream;
import org.springframework.stereotype.Component;

@Component
public class CatalogImageProcessor implements PhotoImages {

    private static final byte[] PNG = {(byte) 137, 80, 78, 71, 13, 10, 26, 10};

    @Override
    public Pixels normalize(byte[] content) {
        if (content.length > 10_000_000) {
            throw new PhotoFailure(Reason.TOO_LARGE);
        }
        try {
            return decode(content);
        } catch (IOException | IllegalArgumentException error) {
            throw new PhotoFailure(Reason.INVALID_IMAGE);
        }
    }

    private Pixels decode(byte[] content) throws IOException {
        boolean png = content.length >= 8 && Arrays.equals(PNG, Arrays.copyOf(content, 8));
        boolean jpeg = content.length >= 3 && content[0] == (byte) 255
            && content[1] == (byte) 216 && content[2] == (byte) 255;
        if (!png && !jpeg) {
            throw new PhotoFailure(Reason.INVALID_IMAGE);
        }
        try (var input = new MemoryCacheImageInputStream(new ByteArrayInputStream(content))) {
            var readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw new PhotoFailure(Reason.INVALID_IMAGE);
            }
            ImageReader reader = readers.next();
            try {
                reader.setInput(input, true, true);
                String format = reader.getFormatName();
                if (!(png && format.equalsIgnoreCase("png") || jpeg && format.equalsIgnoreCase("jpeg"))) {
                    throw new PhotoFailure(Reason.INVALID_IMAGE);
                }
                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                if (width < 1 || height < 1 || width > 8192 || height > 8192 || (long) width * height > 16_000_000) {
                    throw new PhotoFailure(Reason.INVALID_IMAGE);
                }
                BufferedImage decoded = reader.read(0);
                if (decoded == null) {
                    throw new PhotoFailure(Reason.INVALID_IMAGE);
                }
                BufferedImage normalized = resize(decoded, width, height);
                double scale = Math.min(1.0, 320.0 / Math.max(width, height));
                BufferedImage thumbnail = resize(decoded, Math.max(1, (int) (width * scale)),
                    Math.max(1, (int) (height * scale)));
                return new Pixels(encode(normalized), encode(thumbnail));
            } finally {
                reader.dispose();
            }
        }
    }

    private BufferedImage resize(BufferedImage source, int width, int height) {
        var output = new BufferedImage(width, height, BufferedImage.TYPE_INT_ARGB);
        var graphics = output.createGraphics();
        try {
            graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            graphics.drawImage(source, 0, 0, width, height, null);
        } finally {
            graphics.dispose();
        }
        return output;
    }

    private byte[] encode(BufferedImage image) throws IOException {
        var output = new LimitedOutput();
        ImageIO.write(image, "png", output);
        if (output.size() > 10_000_000) {
            throw new PhotoFailure(Reason.TOO_LARGE);
        }
        return output.toByteArray();
    }

    private static final class LimitedOutput extends ByteArrayOutputStream {

        @Override
        public synchronized void write(byte[] bytes, int offset, int length) {
            if ((long) count + length > 10_000_000) {
                throw new PhotoFailure(Reason.TOO_LARGE);
            }
            super.write(bytes, offset, length);
        }

        @Override
        public synchronized void write(int value) {
            if (count >= 10_000_000) {
                throw new PhotoFailure(Reason.TOO_LARGE);
            }
            super.write(value);
        }
    }
}
