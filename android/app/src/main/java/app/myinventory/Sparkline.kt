package app.myinventory

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.view.View

/** 7-day mini chart, old to new left to right (same shape as the web sparkline). */
class Sparkline(context: Context, private val points: List<Double>, color: Int) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = resources.displayMetrics.density * 1.6f
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
        this.color = color
    }

    override fun onDraw(canvas: Canvas) {
        if (points.size < 2) return
        val pad = paint.strokeWidth * 2
        val w = width - pad * 2
        val h = height - pad * 2
        val min = points.min()
        val span = points.max() - min
        val path = Path()
        points.forEachIndexed { i, v ->
            val x = pad + w * i / (points.size - 1)
            val y = if (span <= 0) pad + h / 2 else pad + h - ((v - min) / span * h).toFloat()
            if (i == 0) path.moveTo(x.toFloat(), y.toFloat()) else path.lineTo(x.toFloat(), y.toFloat())
        }
        canvas.drawPath(path, paint)
    }
}
