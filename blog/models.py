from django.db import models
from django.urls import reverse

class Post(models.Model):


    class Meta:
        verbose_name = ("")
        verbose_name_plural = ("s")

    def __str__(self):
        return self.name
